"""Pushbullet notification sending and main handlers for Claude Code notifications."""

import argparse
import json
import logging
import os
import subprocess

from .config import CONFIG, DEFAULT_MAX_BODY_LENGTH, DEFAULT_SPLIT_LONG_MESSAGES
from .template import _format_template, _get_template_variables, get_git_info
from .transcript import (
    _add_part_numbers_to_title,
    _split_message_into_chunks,
    get_last_messages_from_transcript,
    read_hook_input,
)

logger = logging.getLogger(__name__)


# Pushbullet API functions


def _get_pushbullet_token():
    """Get Pushbullet token from environment or config."""
    token = os.environ.get("PUSHBULLET_TOKEN")
    if not token and "token" in CONFIG.get("pushbullet", {}):
        token = CONFIG["pushbullet"]["token"]
    return token


def _send_via_requests(token, payload):
    """Send notification using requests library."""
    import requests

    response = requests.post(
        "https://api.pushbullet.com/v2/pushes",
        headers={"Access-Token": token, "Content-Type": "application/json"},
        json=payload,
    )
    return response.status_code == 200


def _send_via_curl(token, payload):
    """Send notification using curl command."""
    result = subprocess.run(
        [
            "curl",
            "-s",
            "-u",
            f"{token}:",
            "-X",
            "POST",
            "https://api.pushbullet.com/v2/pushes",
            "-H",
            "Content-Type: application/json",
            "--data-raw",
            json.dumps(payload),
        ],
        capture_output=True,
    )
    return result.returncode == 0


def send_pushbullet_notification(title, body):
    """Send notification via Pushbullet API."""
    token = _get_pushbullet_token()
    if not token:
        logger.error("PUSHBULLET_TOKEN not set. Please set it in environment variable or config.toml")
        return False

    payload = {"type": "note", "title": title, "body": body}

    try:
        return _send_via_requests(token, payload)
    except ImportError:
        # Fallback to curl if requests is not available
        return _send_via_curl(token, payload)


# Split notification functions


def _get_split_config(max_length, split_enabled):
    """Get splitting configuration from parameters or config."""
    if max_length is None:
        max_length = CONFIG.get("notification", {}).get("max_body_length", DEFAULT_MAX_BODY_LENGTH)
    if split_enabled is None:
        split_enabled = CONFIG.get("notification", {}).get("split_long_messages", DEFAULT_SPLIT_LONG_MESSAGES)
    split_delay_ms = CONFIG.get("notification", {}).get("split_delay_ms", 0)
    return max_length, split_enabled, split_delay_ms


def _calculate_reserve_space(body_length, max_length):
    """Calculate space needed for numbering in multi-part messages."""
    estimated_chunks = (body_length // max_length) + 1
    if estimated_chunks < 10:
        return 6  # "[1/9] " = 6 chars
    elif estimated_chunks < 100:
        return 8  # "[10/99] " = 8 chars
    else:
        return 10  # "[100/999] " = 10 chars


def _send_single_chunk(title, body, chunks):
    """Send a single chunk without numbering."""
    return send_pushbullet_notification(title, chunks[0] if chunks else body)


def _send_numbered_chunk(title, chunk, part_num, total_parts):
    """Send a numbered chunk and log the result."""
    numbered_title = _add_part_numbers_to_title(title, part_num, total_parts)
    success = send_pushbullet_notification(numbered_title, chunk)

    if not success:
        logger.error(f"Failed to send part {part_num}/{total_parts}")
    else:
        logger.info(f"Sent part {part_num}/{total_parts}")

    return success


def _apply_notification_delay(split_delay_ms):
    """Apply delay between notifications if configured."""
    if split_delay_ms > 0:
        import time

        time.sleep(split_delay_ms / 1000.0)


def send_split_notifications(title, body, max_length=None, split_enabled=None):
    """Send notifications, splitting long messages if needed.

    Args:
        title: Notification title
        body: Notification body
        max_length: Maximum length per notification (uses config if None)
        split_enabled: Whether to split messages (uses config if None)

    Returns:
        True if all notifications sent successfully, False otherwise
    """
    max_length, split_enabled, split_delay_ms = _get_split_config(max_length, split_enabled)

    # If splitting is disabled or message is short, send as single notification
    if not split_enabled or len(body) <= max_length:
        return send_pushbullet_notification(title, body)

    # Calculate space needed for numbering
    reserve_space = _calculate_reserve_space(len(body), max_length)

    # Split the message into chunks
    chunks = _split_message_into_chunks(body, max_length, reserve_space)

    # If only one chunk after splitting, send without numbering
    if len(chunks) <= 1:
        return _send_single_chunk(title, body, chunks)

    # Send each chunk with numbering
    all_success = True
    for i, chunk in enumerate(chunks, 1):
        success = _send_numbered_chunk(title, chunk, i, len(chunks))
        if not success:
            all_success = False

        # Add delay between notifications (except for last one)
        if i < len(chunks):
            _apply_notification_delay(split_delay_ms)

    return all_success


# Main notification function


def _send_notification(repo_name, branch_name, notification_body, transcript_path=None):
    """Send notification with template-based or standard title format."""
    variables = _get_template_variables(repo_name, branch_name, transcript_path)

    # Use template from config if available, otherwise use default
    title_template = CONFIG.get("notification", {}).get(
        "title_template", "claude code task completed {GIT_REPO} {GIT_BRANCH}"
    )
    title = _format_template(title_template, variables)

    # Check if there's a custom body template
    body_template = CONFIG.get("notification", {}).get("body_template")
    if body_template:
        notification_body = _format_template(body_template, variables)

    logger.info(f"Sending notification: {title}")

    if notification_body and len(notification_body) > 100:
        logger.debug(f"Notification body: {notification_body[:100]}...")
    elif notification_body:
        logger.debug(f"Notification body: {notification_body}")

    # Use the new split notification function
    result = send_split_notifications(title, notification_body)
    logger.info(f"Notification sent: {result}")
    return result


# Event handlers


def _handle_test_mode(args):
    """Handle test mode execution."""
    logger.info("Running in test mode")
    repo_name, branch_name = get_git_info()
    logger.info(f"Repository: {repo_name}, Branch: {branch_name}")

    if args.transcript_path:
        notification_body = get_last_messages_from_transcript(args.transcript_path)
        transcript_path = args.transcript_path
    else:
        notification_body = "Test mode - no transcript available"
        transcript_path = None

    _send_notification(repo_name, branch_name, notification_body, transcript_path)


def _log_stop_event_details(hook_data):
    """Log details about the stop event."""
    transcript_path = hook_data.get("transcript_path")
    logger.debug(f"Transcript path: {transcript_path}")
    logger.debug(f"Stop hook active: {hook_data.get('stop_hook_active')}")
    return transcript_path


def _log_config_details():
    """Log configuration details."""
    logger.debug(
        f"Config: num_messages={CONFIG.get('notification', {}).get('num_messages', 3)}, "
        f"max_body_length={CONFIG.get('notification', {}).get('max_body_length', 1000)}"
    )


def _handle_stop_event(hook_data):
    """Handle Stop event from hook."""
    transcript_path = _log_stop_event_details(hook_data)

    if not transcript_path:
        logger.warning("No transcript path provided")
        return

    repo_name, branch_name = get_git_info()
    notification_body = get_last_messages_from_transcript(transcript_path)
    _log_config_details()
    _send_notification(repo_name, branch_name, notification_body, transcript_path)


def _handle_hook_mode(hook_data):
    """Handle hook mode execution."""
    hook_event = hook_data.get("hook_event_name", "")
    logger.info(f"Hook event: {hook_event}")

    if hook_event == "Stop":
        _handle_stop_event(hook_data)
    else:
        logger.info(f"Skipping - Event: {hook_event} (not Stop)")


def _handle_legacy_mode():
    """Handle legacy fallback mode."""
    logger.info("No JSON input received. Running in legacy test mode")
    repo_name, branch_name = get_git_info()
    logger.info(f"Repository: {repo_name}, Branch: {branch_name}")
    notification_body = "Test mode - no transcript available"
    _send_notification(repo_name, branch_name, notification_body, None)


# Main entry point


def main():
    """Main function for the Claude Code hook."""
    parser = argparse.ArgumentParser(description="Claude Code Pushbullet notification hook")
    parser.add_argument("--test", action="store_true", help="Run in test mode")
    parser.add_argument("--transcript-path", help="Path to transcript file for testing")
    args = parser.parse_args()

    if args.test:
        _handle_test_mode(args)
        return

    hook_data = read_hook_input()
    if hook_data:
        _handle_hook_mode(hook_data)
    else:
        _handle_legacy_mode()
