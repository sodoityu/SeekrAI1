#!/usr/bin/env python3
"""
Standalone Slack Search - Uses MCP SDK (same pattern as daily_briefing.py)
Can be run via systemd/cron without Claude Code

Usage:
  poetry run python slack_search_standalone.py "HCP allowedRegistries"
  poetry run python slack_search_standalone.py "upgrade stuck" --limit 20 --output results.txt
"""
import asyncio
import json
import sys
import argparse
from datetime import datetime
from typing import List

# Same imports as daily_briefing.py
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    print("Error: MCP SDK not installed.")
    print("Install it with: poetry add mcp")
    sys.exit(1)


class SlackSearch:
    def __init__(self, config_path: str = '.mcp.json'):
        """Initialize using MCP configuration."""
        import os

        with open(config_path, 'r') as f:
            config = json.load(f)
        self.slack_config = config['mcpServers']['slack']

        # Override with environment variables if set (for UI credentials)
        if os.getenv('SLACK_XOXC_TOKEN'):
            self.slack_config['env']['SLACK_XOXC_TOKEN'] = os.getenv('SLACK_XOXC_TOKEN')
        if os.getenv('SLACK_XOXD_TOKEN'):
            self.slack_config['env']['SLACK_XOXD_TOKEN'] = os.getenv('SLACK_XOXD_TOKEN')
        if os.getenv('SLACK_WORKSPACE_URL'):
            self.slack_config['env']['SLACK_WORKSPACE_URL'] = os.getenv('SLACK_WORKSPACE_URL')
        if os.getenv('LOGS_CHANNEL_ID'):
            self.slack_config['env']['LOGS_CHANNEL_ID'] = os.getenv('LOGS_CHANNEL_ID')

        # Get credentials for direct API calls
        self.xoxc_token = self.slack_config['env'].get('SLACK_XOXC_TOKEN', '')
        self.xoxd_token = self.slack_config['env'].get('SLACK_XOXD_TOKEN', '')
        self.workspace_url = self.slack_config['env'].get('SLACK_WORKSPACE_URL', 'https://redhat.enterprise.slack.com')

        # Get logs channel ID to filter out log messages
        self.logs_channel_id = self.slack_config['env'].get('LOGS_CHANNEL_ID', '')

    async def search_messages(self, query: str, limit: int = 50, include_context: bool = False, context_size: int = 3) -> List[dict]:
        """
        Search Slack messages using Slack Web API (with channel info) or MCP as fallback.

        Args:
            query: Search query
            limit: Max results to return
            include_context: If True, fetch messages before/after each result
            context_size: Number of messages to fetch before/after (default: 3)

        Returns:
            List of message dicts with channel_id populated
        """
        # Try Slack Web API first (has channel info)
        try:
            api_results = self._search_slack_api(query, limit)
            if api_results:
                return api_results
        except Exception as e:
            print(f"Warning: Slack API search failed, falling back to MCP: {e}", file=sys.stderr)

        # Fall back to MCP method (no channel info)
        # Extract channel name from query if present (e.g., "query in:#channel")
        import re
        channel_match = re.search(r'in:#([\w-]+)', query)
        default_channel = channel_match.group(1) if channel_match else None

        server_params = StdioServerParameters(
            command=self.slack_config['command'],
            args=self.slack_config['args'],
            env=self.slack_config['env']
        )

        messages = []

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Call search_messages tool
                result = await session.call_tool(
                    "search_messages",
                    arguments={
                        "query": query,
                        "limit": limit,
                        "sort": "timestamp"
                    }
                )

                # Parse results (same as daily_briefing.py)
                if result.content:
                    for content_item in result.content:
                        if hasattr(content_item, 'text'):
                            text = content_item.text.strip()

                            # Skip debug/log messages from MCP server
                            if text.startswith(("Searching", "Found", "No messages", "Error")):
                                continue

                            # Skip empty lines
                            if not text:
                                continue

                            try:
                                # Try parsing as JSON first
                                data = json.loads(text)
                                if isinstance(data, dict) and 'result' in data:
                                    msgs = data['result']
                                elif isinstance(data, list):
                                    msgs = data
                                else:
                                    msgs = [text]
                            except json.JSONDecodeError:
                                # Not JSON, treat as plain text message
                                msgs = [text]

                            # Process each message
                            for msg in msgs:
                                if isinstance(msg, str):
                                    # Skip if it's a log message that got through
                                    if msg.startswith(("Searching", "Found", "No messages", "Error", "Retrieved")):
                                        continue

                                    parsed = self.parse_message(msg)

                                    # Try to extract channel from Slack links in message text
                                    if not parsed.get('channel_id'):
                                        channel_from_link = self._extract_channel_from_links(parsed.get('text', ''))
                                        if channel_from_link:
                                            parsed['channel_id'] = channel_from_link

                                    # If no channel in message, use channel from query
                                    if not parsed.get('channel_id') and not parsed.get('channel_name'):
                                        if default_channel:
                                            parsed['channel_name'] = default_channel

                                    # Skip messages from the logs channel (MCP debug output)
                                    if self.logs_channel_id and parsed.get('channel_id') == self.logs_channel_id:
                                        continue

                                    # Skip if we couldn't parse it properly (no user or timestamp)
                                    if parsed.get('user') == 'unknown' and not parsed.get('timestamp'):
                                        continue

                                    # Skip if text looks like a log message
                                    text = parsed.get('text', '')
                                    if text.startswith(("Searching for messages:", "Found ", "Retrieved ", "No messages")):
                                        continue

                                    # If context requested, fetch surrounding messages
                                    if include_context and parsed.get('channel_id') and parsed.get('ts'):
                                        try:
                                            context = await self._fetch_context(
                                                session,
                                                parsed['channel_id'],
                                                float(parsed['ts']),
                                                context_size
                                            )
                                            parsed['context_before'] = context['before']
                                            parsed['context_after'] = context['after']
                                        except Exception as e:
                                            # If context fetch fails, continue without it
                                            parsed['context_before'] = []
                                            parsed['context_after'] = []

                                    messages.append(parsed)
                                elif isinstance(msg, dict):
                                    # If it's already a dict, use it directly
                                    # But also skip if from logs channel
                                    if self.logs_channel_id and msg.get('channel_id') == self.logs_channel_id:
                                        continue
                                    messages.append(msg)

        return messages

    async def _fetch_context(self, session, channel_id: str, timestamp: float, size: int = 3) -> dict:
        """
        Fetch messages before and after a specific timestamp.

        Args:
            session: MCP session
            channel_id: Channel ID
            timestamp: Message timestamp
            size: Number of messages before/after to fetch

        Returns:
            Dict with 'before' and 'after' message lists
        """
        context = {'before': [], 'after': []}

        try:
            # Fetch messages before (oldest=timestamp-window, latest=timestamp)
            # and after (oldest=timestamp, latest=timestamp+window)
            # We'll fetch a window and filter

            # Fetch some messages around the timestamp
            window_seconds = 3600  # 1 hour window
            oldest = timestamp - window_seconds
            latest = timestamp + window_seconds

            result = await session.call_tool(
                "get_channel_history",
                arguments={
                    "channel_id": channel_id,
                    "oldest": str(oldest),
                    "latest": str(latest),
                    "limit": 50
                }
            )

            # Parse and sort messages by timestamp
            all_msgs = []
            if result.content:
                for content_item in result.content:
                    if hasattr(content_item, 'text'):
                        msg_text = content_item.text.strip()
                        if msg_text and not msg_text.startswith(("Fetching", "Found")):
                            parsed = self.parse_message(msg_text)
                            if 'ts' in parsed:
                                all_msgs.append(parsed)

            # Sort by timestamp
            all_msgs.sort(key=lambda m: float(m.get('ts', 0)))

            # Split into before/after based on the target timestamp
            for msg in all_msgs:
                msg_ts = float(msg.get('ts', 0))
                if msg_ts < timestamp:
                    context['before'].append(msg)
                elif msg_ts > timestamp:
                    context['after'].append(msg)

            # Keep only the requested number of messages
            context['before'] = context['before'][-size:]  # Last N before
            context['after'] = context['after'][:size]  # First N after

        except Exception as e:
            # If context fetch fails, return empty
            pass

        return context

    def _search_slack_api(self, query: str, limit: int = 50) -> List[dict]:
        """
        Search Slack messages using the Web API directly to get channel information.

        Args:
            query: Search query
            limit: Max results to return

        Returns:
            List of message dicts with channel_id populated
        """
        import requests
        from urllib.parse import quote

        if not self.xoxc_token or not self.xoxd_token:
            return []

        # Slack Web API search.messages endpoint
        url = "https://slack.com/api/search.messages"

        # Cookies for authentication
        cookies = {
            'd': self.xoxd_token,
            'd-s': '1779009000'  # Session timestamp
        }

        # Headers
        headers = {
            'Authorization': f'Bearer {self.xoxc_token}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        # Parameters
        params = {
            'query': query,
            'count': min(limit, 100),  # Max 100 per page
            'sort': 'timestamp',
            'sort_dir': 'desc'
        }

        try:
            response = requests.get(url, params=params, headers=headers, cookies=cookies, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not data.get('ok'):
                return []

            messages = []
            if 'messages' in data and 'matches' in data['messages']:
                for match in data['messages']['matches']:
                    # Extract channel info
                    channel_info = match.get('channel', {})
                    channel_id = channel_info.get('id', '')
                    channel_name = channel_info.get('name', '')

                    # Parse message
                    msg = {
                        'user': match.get('username', 'unknown'),
                        'text': match.get('text', ''),
                        'ts': match.get('ts', ''),
                        'channel_id': channel_id,
                        'channel_name': channel_name
                    }

                    # Format timestamp
                    if msg['ts']:
                        try:
                            ts_float = float(msg['ts'])
                            dt = datetime.fromtimestamp(ts_float)
                            msg['timestamp'] = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            msg['timestamp'] = str(msg['ts'])
                    else:
                        msg['timestamp'] = ''

                    messages.append(msg)

            return messages

        except Exception as e:
            print(f"Warning: Slack API search failed: {e}", file=sys.stderr)
            return []

    def _extract_channel_from_links(self, text: str) -> str:
        """
        Extract channel ID from Slack archive links in message text.

        Args:
            text: Message text that may contain Slack links

        Returns:
            Channel ID if found, empty string otherwise
        """
        import re
        # Match Slack archive links like:
        # https://redhat-internal.slack.com/archives/C04JNBT3BNZ/p1777613176596659
        # https://slack.com/archives/C04JNBT3BNZ/p1777613176596659
        pattern = r'https://[^/]*slack\.com/archives/([A-Z0-9]+)/p\d+'
        match = re.search(pattern, text)
        if match:
            return match.group(1)
        return ""

    def parse_message(self, msg_text: str) -> dict:
        """
        Parse message from various formats.

        Expected formats:
        - '[timestamp] @user: text'
        - '[timestamp] #channel @user: text'
        - JSON string with message data
        """
        # Try parsing as JSON first (for structured MCP output)
        try:
            if msg_text.strip().startswith('{'):
                data = json.loads(msg_text)
                if isinstance(data, dict):
                    # Extract fields from JSON
                    result = {
                        "user": data.get('user', data.get('username', 'unknown')),
                        "text": data.get('text', msg_text),
                        "ts": data.get('ts', data.get('timestamp', '')),
                        "channel_id": data.get('channel', data.get('channel_id', ''))
                    }

                    # Format timestamp for display
                    if result['ts']:
                        try:
                            ts_float = float(result['ts'])
                            dt = datetime.fromtimestamp(ts_float)
                            result['timestamp'] = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            result['timestamp'] = str(result['ts'])
                    else:
                        result['timestamp'] = ''

                    return result
        except json.JSONDecodeError:
            pass

        # Parse text format: '[timestamp] #channel @user: text' or '[timestamp] @user: text'
        try:
            parts = msg_text.split('] ', 1)
            if len(parts) == 2:
                timestamp = parts[0].strip('[')
                rest = parts[1]

                # Check if channel is present
                channel_id = ''
                channel_name = ''
                if rest.startswith('#'):
                    channel_parts = rest.split(' ', 1)
                    if len(channel_parts) == 2:
                        channel_name = channel_parts[0].strip('#')
                        channel_id = channel_name
                        rest = channel_parts[1]

                user_parts = rest.split(': ', 1)
                if len(user_parts) == 2:
                    user = user_parts[0].strip('@')
                    text = user_parts[1]

                    # Format timestamp
                    try:
                        ts = float(timestamp)
                        dt = datetime.fromtimestamp(ts)
                        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        time_str = timestamp
                        ts = timestamp

                    return {
                        "user": user,
                        "timestamp": time_str,
                        "ts": str(ts),
                        "text": text,
                        "channel_id": channel_id,
                        "channel_name": channel_name
                    }
        except:
            pass

        return {
            "user": "unknown",
            "timestamp": "",
            "ts": "",
            "text": msg_text,
            "channel_id": "",
            "channel_name": ""
        }

    def format_results(self, messages: List, query: str, max_chars: int = None) -> str:
        """Format results for display."""
        lines = []
        lines.append("=" * 80)
        lines.append(f"Slack Search Results: {query}")
        lines.append(f"Found: {len(messages)} messages")
        lines.append(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)
        lines.append("")

        for i, msg in enumerate(messages, 1):
            # Handle both dict and string formats
            if isinstance(msg, str):
                msg = self.parse_message(msg)

            # Show context messages if present
            if 'context_before' in msg and msg['context_before']:
                lines.append("  ┌─── Context (before) ───")
                for ctx_msg in msg['context_before']:
                    lines.append(f"  │ @{ctx_msg.get('user', 'unknown')} - {ctx_msg.get('timestamp', '')}")
                    ctx_text = ctx_msg.get('text', '')
                    if max_chars and len(ctx_text) > max_chars:
                        ctx_text = ctx_text[:max_chars] + "..."
                    lines.append(f"  │ {ctx_text}")
                    lines.append("  │")
                lines.append("  └────────────────────────")

            # Main message (highlighted)
            lines.append(f"{i}. ⭐ @{msg.get('user', 'unknown')} - {msg.get('timestamp', '')}")
            text = msg.get('text', '')
            if max_chars and len(text) > max_chars:
                text = text[:max_chars] + "..."
            lines.append(f"   {text}")

            # Show context after if present
            if 'context_after' in msg and msg['context_after']:
                lines.append("  ┌─── Context (after) ────")
                for ctx_msg in msg['context_after']:
                    lines.append(f"  │ @{ctx_msg.get('user', 'unknown')} - {ctx_msg.get('timestamp', '')}")
                    ctx_text = ctx_msg.get('text', '')
                    if max_chars and len(ctx_text) > max_chars:
                        ctx_text = ctx_text[:max_chars] + "..."
                    lines.append(f"  │ {ctx_text}")
                    lines.append("  │")
                lines.append("  └────────────────────────")

            lines.append("")

        lines.append("=" * 80)
        return "\n".join(lines)


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Search Slack using MCP (same as daily_briefing.py pattern)'
    )
    parser.add_argument('query', help='Search query')
    parser.add_argument('--limit', type=int, default=50, help='Max results (default: 50)')
    parser.add_argument('--output', '-o', help='Save results to file')
    parser.add_argument('--truncate', type=int, help='Truncate messages to N characters (default: no truncation)')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')
    parser.add_argument('--context', action='store_true', help='Include messages before/after each result')
    parser.add_argument('--context-size', type=int, default=3, help='Number of messages before/after (default: 3)')

    args = parser.parse_args()

    print(f"\n{'=' * 80}")
    print(f"Slack Search (MCP SDK)")
    print(f"{'=' * 80}")
    print(f"Query: {args.query}")
    print(f"Limit: {args.limit}")
    if args.context:
        print(f"Context: {args.context_size} messages before/after")
    print(f"{'=' * 80}\n")

    # Initialize searcher
    searcher = SlackSearch()

    # Search
    if not args.json:
        print("🔍 Searching Slack via MCP...")

    try:
        messages = await searcher.search_messages(
            args.query,
            args.limit,
            include_context=args.context,
            context_size=args.context_size
        )

        if args.json:
            # JSON output for web UI
            result = {
                "ok": True,
                "messages": messages,
                "total": len(messages),
                "query": args.query,
                "has_context": args.context
            }
            print(json.dumps(result))
        else:
            # Human-readable output
            print(f"✅ Found {len(messages)} messages\n")

            # Format results
            output = searcher.format_results(messages, args.query, max_chars=args.truncate)
            print(output)

            # Save to file if requested
            if args.output:
                with open(args.output, 'w') as f:
                    f.write(output)
                print(f"\n💾 Results saved to: {args.output}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
