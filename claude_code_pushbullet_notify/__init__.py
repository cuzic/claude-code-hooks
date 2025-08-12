"""
Claude Code hook for sending Pushbullet notifications when tasks complete.
Reads JSON from stdin and processes transcript files.
"""

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import tomllib
from dotenv import load_dotenv

# Load environment variables from .env file in project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Default configuration
DEFAULT_NUM_MESSAGES = 3
DEFAULT_MAX_BODY_LENGTH = 1000
DEFAULT_SPLIT_LONG_MESSAGES = True


def merge_configs(default, loaded):
    """Recursively merge two configuration dictionaries."""
    result = default.copy()
    for key, value in loaded.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def load_config():
    """Load configuration from config.toml file."""
    config_path = Path(__file__).parent.parent / "config.toml"
    config = {
        "notification": {
            "num_messages": DEFAULT_NUM_MESSAGES,
            "max_body_length": DEFAULT_MAX_BODY_LENGTH,
            "split_long_messages": DEFAULT_SPLIT_LONG_MESSAGES,
        },
        "pushbullet": {},
        "logging": {"debug": True, "log_file": "claude-code-pushbullet-notify.log"},
    }

    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                loaded_config = tomllib.load(f)
                # Recursively merge loaded config with defaults
                config = merge_configs(config, loaded_config)
        except Exception as e:
            logging.error(f"Error loading config: {e}")

    return config


# Load configuration on import
CONFIG = load_config()


# Set up logging
def setup_logging():
    """Configure logging based on config settings."""
    log_level = logging.DEBUG if CONFIG["logging"]["debug"] else logging.INFO
    log_file = Path(__file__).parent.parent / CONFIG["logging"]["log_file"]

    # Configure logging to file and stderr
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stderr)],
    )


setup_logging()
logger = logging.getLogger(__name__)


def read_hook_input():
    """Read JSON input from stdin for the hook."""
    try:
        # Read from stdin
        input_data = sys.stdin.read()
        if not input_data:
            return None

        # Parse JSON
        hook_data = json.loads(input_data)
        return hook_data
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error reading hook input: {e}")
        return None


def _get_git_info_from_env():
    """Get git info from environment variables."""
    repo_name = os.environ.get("HOOK_GIT_REPO")
    branch_name = os.environ.get("HOOK_GIT_BRANCH")
    if repo_name and branch_name:
        return repo_name, branch_name
    return None, None


def _get_repo_name_from_git(cwd):
    """Get repository name using git command."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], 
        capture_output=True, text=True, check=True, cwd=cwd
    )
    repo_path = Path(result.stdout.strip())
    return repo_path.name.replace(".git", "")


def _get_branch_name_from_git(cwd):
    """Get branch name using git command."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], 
        capture_output=True, text=True, check=True, cwd=cwd
    )
    return result.stdout.strip()


def get_git_info():
    """Get repository name and branch name from git."""
    # First check environment variables
    repo_name, branch_name = _get_git_info_from_env()
    if repo_name and branch_name:
        return repo_name, branch_name

    # Fallback to git commands
    try:
        cwd = os.getcwd()
        repo_name = _get_repo_name_from_git(cwd)
        branch_name = _get_branch_name_from_git(cwd)
        return repo_name, branch_name
    except subprocess.CalledProcessError:
        # If not in a git repo, use the current directory name
        return Path.cwd().name, "main"


def _extract_text_from_list(content_list):
    """Extract text from a list of content items."""
    texts = []
    for item in content_list:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text", "").strip()
        if text:
            texts.append(text)
    return texts


def _extract_message_text(content):
    """Extract text from message content (string or list format)."""
    if isinstance(content, str):
        return [content]

    if isinstance(content, list):
        return _extract_text_from_list(content)

    return []


def _is_assistant_message(data):
    """Check if data represents an assistant message."""
    if data.get("type") != "assistant":
        return False
    if "message" not in data:
        return False
    msg = data["message"]
    return msg.get("role") == "assistant" and "content" in msg


def _parse_json_line(line, line_number):
    """Parse a JSON line and handle errors."""
    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        logger.debug(f"Line {line_number}: Skipping invalid JSON - {e}")
        return None


def _process_transcript_line(line, line_number):
    """Process a single transcript line and extract assistant messages."""
    data = _parse_json_line(line, line_number)
    if data is None:
        return []
    
    if not _is_assistant_message(data):
        return []
    
    return _extract_message_text(data["message"]["content"])


def _read_transcript_messages(transcript_path):
    """Read all assistant messages from transcript file."""
    messages = []
    with open(transcript_path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            messages.extend(_process_transcript_line(line, line_number))
    return messages


def _calculate_effective_max_length(max_length, reserve_space):
    """Calculate effective maximum length after reserving space."""
    effective_max_length = max_length - reserve_space
    if effective_max_length <= 0:
        effective_max_length = max_length  # Fallback if reserve_space is too large
    return effective_max_length


def _should_add_overlap(chunks, previous_paragraph, effective_max_length):
    """Check if overlap should be added from previous paragraph."""
    return (chunks and previous_paragraph and 
            len(previous_paragraph) < effective_max_length // 3)


def _split_by_sentences(text, max_length):
    """Split text by sentence boundaries."""
    sentences = text.replace('. ', '.|').split('|')
    chunks = []
    current = ""
    
    for sentence in sentences:
        # If a single sentence is longer than max_length, split by words
        if len(sentence) > max_length:
            if current:
                chunks.append(current)
                current = ""
            word_chunks = _split_by_words(sentence, max_length)
            if word_chunks:
                chunks.extend(word_chunks[:-1])  # Add all but last
                current = word_chunks[-1] if word_chunks else ""
        else:
            test = current + sentence if current else sentence
            if len(test) <= max_length:
                current = test
            else:
                if current:
                    chunks.append(current)
                current = sentence
    
    if current:
        chunks.append(current)
    return chunks


def _split_by_characters(text, max_length):
    """Split text by character boundaries when it cannot be split by words."""
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        chunks.append(text[:max_length])
        text = text[max_length:]
    return chunks


def _split_by_words(text, max_length):
    """Split text by word boundaries."""
    words = text.split(' ')
    chunks = []
    current = ""
    
    for word in words:
        # If a single word is longer than max_length, split it by characters
        if len(word) > max_length:
            if current:
                chunks.append(current)
                current = ""
            char_chunks = _split_by_characters(word, max_length)
            chunks.extend(char_chunks)
        else:
            test = current + " " + word if current else word
            if len(test) <= max_length:
                current = test
            else:
                if current:
                    chunks.append(current)
                current = word
    
    if current:
        chunks.append(current)
    return chunks


def _handle_paragraph_overlap(current_chunk, paragraph, previous_paragraph, 
                             effective_max_length, chunks):
    """Handle adding paragraph with potential overlap."""
    test_with_overlap = previous_paragraph + "\n\n" + paragraph
    
    if len(test_with_overlap) <= effective_max_length:
        # Can fit both with overlap
        if current_chunk and len(current_chunk + "\n\n" + test_with_overlap) > effective_max_length:
            # Save current chunk and start new one with overlap
            chunks.append(current_chunk)
            return test_with_overlap, True
        else:
            # Add to current chunk
            if current_chunk:
                return current_chunk + "\n\n" + test_with_overlap, True
            else:
                return test_with_overlap, True
    
    return current_chunk, False


def _process_paragraph(current_chunk, paragraph, previous_paragraph,
                      effective_max_length, chunks):
    """Process a single paragraph and update chunks."""
    # Try to add paragraph to current chunk
    test_chunk = current_chunk + "\n\n" + paragraph if current_chunk else paragraph
    
    if len(test_chunk) <= effective_max_length:
        # Fits in current chunk
        return test_chunk, paragraph
    
    # Doesn't fit, need to handle it
    if current_chunk:
        chunks.append(current_chunk)
        
        # Start new chunk with overlap if appropriate
        if previous_paragraph and len(previous_paragraph) < effective_max_length // 3:
            new_chunk = previous_paragraph + "\n\n" + paragraph
            if len(new_chunk) > effective_max_length:
                new_chunk = paragraph
        else:
            new_chunk = paragraph
    else:
        new_chunk = paragraph
    
    # If single paragraph is too long, split it
    if len(new_chunk) > effective_max_length:
        split_chunks = _split_by_sentences(new_chunk, effective_max_length)
        if split_chunks:
            chunks.extend(split_chunks[:-1])  # Add all but last
            new_chunk = split_chunks[-1]
    
    return new_chunk, paragraph


def _split_message_into_chunks(message, max_length, reserve_space=0):
    """Split a message into chunks with paragraph-level overlap for context.
    
    Args:
        message: The message to split
        max_length: Maximum length for each chunk
        reserve_space: Space to reserve for numbering (e.g., "[10/10] " = 8 chars)
    
    Returns:
        List of message chunks with overlap for context continuity
    """
    if not message:
        return []
    
    effective_max_length = _calculate_effective_max_length(max_length, reserve_space)
    
    # If message fits in one chunk, return as is
    if len(message) <= effective_max_length:
        return [message]
    
    chunks = []
    paragraphs = message.split('\n\n')  # Split by double newline (paragraphs)
    
    current_chunk = ""
    previous_paragraph = ""  # Store last paragraph for overlap
    
    for paragraph in paragraphs:
        # Check for overlap handling
        if _should_add_overlap(chunks, previous_paragraph, effective_max_length):
            new_chunk, handled = _handle_paragraph_overlap(
                current_chunk, paragraph, previous_paragraph, 
                effective_max_length, chunks
            )
            if handled:
                current_chunk = new_chunk
                previous_paragraph = paragraph
                continue
        
        # Process paragraph normally
        current_chunk, previous_paragraph = _process_paragraph(
            current_chunk, paragraph, previous_paragraph,
            effective_max_length, chunks
        )
    
    # Add the last chunk if it exists
    if current_chunk and current_chunk.strip():
        chunks.append(current_chunk)
    
    return chunks


def _add_part_numbers_to_title(title, part_num, total_parts):
    """Add part numbers to a title for multi-part messages.
    
    Args:
        title: The original title
        part_num: Current part number (1-based)
        total_parts: Total number of parts
    
    Returns:
        Title with part numbers if needed
    """
    if total_parts <= 1:
        return title
    
    return f"[{part_num}/{total_parts}] {title}"


def _format_notification_body(messages, num_lines, max_length=None):
    """Format messages for notification body.
    
    Note: max_length is now optional as splitting is handled during sending.
    """
    if not messages:
        return "Task completed."

    last_messages = messages[-num_lines:] if len(messages) > num_lines else messages
    result = "\n\n".join(last_messages)

    # Only truncate if max_length is explicitly provided and splitting is disabled
    if max_length and not CONFIG["notification"].get("split_long_messages", True):
        if len(result) > max_length:
            result = result[: max_length - 3] + "..."

    return result


def get_last_messages_from_transcript(transcript_path, num_lines=None):
    """Get the last N lines from the transcript file."""
    if not transcript_path or not Path(transcript_path).exists():
        return "completed."

    # Use config values if not specified
    if num_lines is None:
        num_lines = CONFIG["notification"]["num_messages"]

    try:
        transcript_path = Path(transcript_path).expanduser()
        messages = _read_transcript_messages(transcript_path)
        # Don't pass max_length anymore as splitting is handled during sending
        return _format_notification_body(messages, num_lines)
    except Exception as e:
        logger.error(f"Error reading transcript: {e}")
        return "Task completed."


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
    import json
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


def _resolve_variable_content(var_content, variables):
    """Resolve a variable name to its content if it exists in variables dict."""
    if variables and var_content in variables:
        return str(variables[var_content])
    return var_content


def _remove_quotes(text):
    """Remove surrounding quotes from text if present."""
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    return text


def _truncate_text(text, length):
    """Truncate text to specified length with ellipsis."""
    if len(text) > length:
        return text[: length - 3] + "..."
    return text


def _apply_truncate_function(text, variables):
    """Apply truncate function to template text."""
    import re
    
    truncate_pattern = r"\{truncate\(\s*([^,)]+?)\s*,\s*(\d+)\s*\)\}"

    def truncate_replace(match):
        var_content = match.group(1).strip()
        var_content = _resolve_variable_content(var_content, variables)
        length = int(match.group(2))
        return _truncate_text(var_content, length)

    return re.sub(truncate_pattern, truncate_replace, text)


def _apply_substr_function(text, variables):
    """Apply substr function to template text."""
    import re
    
    # Handle simple cases with regex
    substr_pattern = r"\{substr\(\s*([^,)]+|\w+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\}"

    def substr_replace(match):
        var_content = match.group(1).strip()
        var_content = _resolve_variable_content(var_content, variables)
        var_content = _remove_quotes(var_content)
        start = int(match.group(2))
        length = int(match.group(3))
        return var_content[start : start + length]

    text = re.sub(substr_pattern, substr_replace, text)
    
    # Handle complex cases with commas
    text = _apply_complex_substr(text, variables)
    return text


def _extract_substr_params(func_content):
    """Extract parameters from substr function content."""
    parts = func_content.rsplit(",", 2)
    if len(parts) != 3:
        return None, None, None
    return parts[0].strip(), parts[1].strip(), parts[2].strip()


def _process_substr_match(text, start_idx, end_idx, variables):
    """Process a single substr function match."""
    func_content = text[start_idx + 8 : end_idx]
    var_content, start_str, length_str = _extract_substr_params(func_content)
    
    if var_content is None:
        return None
        
    var_content = _resolve_variable_content(var_content, variables)
    var_content = _remove_quotes(var_content)
    
    try:
        start_pos = int(start_str)
        length_val = int(length_str)
        replacement = var_content[start_pos : start_pos + length_val]
        return text[:start_idx] + replacement + text[end_idx + 2 :]
    except (ValueError, IndexError):
        return None


def _find_function_bounds(text, func_name):
    """Find the start and end indices of a function call."""
    pattern = f"{{{func_name}("
    start_idx = text.find(pattern)
    if start_idx == -1:
        return None, None
    
    end_idx = text.find(")}", start_idx)
    if end_idx == -1:
        return None, None
    
    return start_idx, end_idx


def _apply_complex_substr(text, variables):
    """Handle substr functions with content containing commas."""
    while True:
        start_idx, end_idx = _find_function_bounds(text, "substr")
        if start_idx is None:
            break

        new_text = _process_substr_match(text, start_idx, end_idx, variables)
        if new_text is None:
            break
        text = new_text
    
    return text


def _extract_regex_params(func_content):
    """Extract parameters from regex function content."""
    parts = func_content.rsplit(",", 1)
    if len(parts) != 2:
        return None, None
    return parts[0].strip(), parts[1].strip()


def _apply_regex_pattern(var_content, pattern):
    """Apply regex pattern to variable content."""
    import re
    
    var_content = _remove_quotes(var_content)
    pattern = _remove_quotes(pattern)
    
    try:
        regex_match = re.search(pattern, var_content)
        return regex_match.group(0) if regex_match else ""
    except re.error:
        return ""


def _process_regex_match(text, start_idx, end_idx, variables):
    """Process a single regex function match."""
    func_content = text[start_idx + 7 : end_idx]  # Skip '{regex('
    
    var_content, pattern = _extract_regex_params(func_content)
    if var_content is None:
        return text[:start_idx] + "" + text[end_idx + 2:]
    
    var_content = _resolve_variable_content(var_content, variables)
    replacement = _apply_regex_pattern(var_content, pattern)
    
    return text[:start_idx] + replacement + text[end_idx + 2:]


def _apply_regex_function(text, variables):
    """Apply regex function to extract text matching a pattern.
    
    Usage: {regex(text, pattern)}
    Example: {regex(MSG0, [0-9]+)} - extracts numbers from MSG0
    """
    while True:
        start_idx, end_idx = _find_function_bounds(text, "regex")
        if start_idx is None:
            break

        text = _process_regex_match(text, start_idx, end_idx, variables)
    
    return text


def _apply_string_functions(text, variables=None):
    """Apply string functions like truncate, substr, and regex to template.

    Args:
        text: The template text with function calls
        variables: Optional dict of template variables to resolve
    """
    text = _apply_truncate_function(text, variables)
    text = _apply_substr_function(text, variables)
    text = _apply_regex_function(text, variables)
    return text


def _format_template(template, variables):
    """Format a template string with provided variables and string functions."""
    if template is None:
        return None
    if not template:
        return ""

    result = template

    # Apply string functions first (they can use variable names)
    # Pass variables so functions can resolve variable names
    result = _apply_string_functions(result, variables)

    # Then replace any remaining variables
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", str(value))

    return result


def _get_tty_direct():
    """Get TTY using the direct tty command."""
    try:
        result = subprocess.run(
            ["tty"], capture_output=True, text=True, check=True
        )
        tty_full = result.stdout.strip()
        # Remove /dev/ prefix if present
        return tty_full.replace("/dev/", "") if tty_full.startswith("/dev/") else tty_full
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _get_tty_for_pid(pid):
    """Try to get TTY for a specific PID using ps command."""
    try:
        result = subprocess.run(
            ["ps", "-o", "tty=", "-p", str(pid)],
            capture_output=True, text=True, check=True
        )
        tty = result.stdout.strip()
        
        # Check if we got a valid TTY (not ? or ??)
        if tty and tty not in ["?", "??", "-"]:
            # Remove /dev/ prefix if present
            return tty.replace("/dev/", "") if tty.startswith("/dev/") else tty
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None


def _get_parent_pid_from_proc(pid):
    """Get parent PID from /proc/{pid}/stat file."""
    try:
        stat_path = f"/proc/{pid}/stat"
        if not os.path.exists(stat_path):
            return None
            
        with open(stat_path, 'r') as f:
            stat_content = f.read()
            # Parent PID is the 4th field in stat file
            # Format: pid (comm) state ppid ...
            # We need to handle comm which might contain spaces and parentheses
            close_paren = stat_content.rfind(')')
            if close_paren == -1:
                return None
                
            fields = stat_content[close_paren + 1:].split()
            if len(fields) >= 2:
                parent_pid = int(fields[1])
                if parent_pid != pid and parent_pid > 1:
                    return parent_pid
    except (IOError, ValueError, IndexError):
        pass
    return None


def _get_tty_from_parent_processes():
    """Get TTY by traversing parent processes using /proc filesystem."""
    try:
        pid = os.getpid()
        
        # Traverse up to 10 parent processes to find a TTY
        for _ in range(10):
            # Try to get TTY for current PID
            tty = _get_tty_for_pid(pid)
            if tty:
                return tty
            
            # Get parent PID and continue traversing
            parent_pid = _get_parent_pid_from_proc(pid)
            if parent_pid is None:
                break
            pid = parent_pid
                
        return "unknown"
        
    except Exception:
        return "unknown"


def _get_system_info():
    """Get system information for template variables."""
    # Get hostname
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"

    # Get username
    username = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

    # Get current working directory
    cwd = os.getcwd()
    
    # Get basename of current working directory
    cwd_basename = os.path.basename(cwd.rstrip(os.sep)) if cwd != os.sep else ""
    
    # Get TTY (terminal) information - try direct method first
    tty = _get_tty_direct()
    
    # If direct TTY detection failed, try traversing parent processes
    if tty == "unknown":
        tty = _get_tty_from_parent_processes()
    
    return hostname, username, cwd, cwd_basename, tty


def _get_time_variables():
    """Get time-related template variables."""
    now = datetime.now()
    return {
        "TIMESTAMP": now.strftime("%Y-%m-%d %H:%M:%S"),
        "DATE": now.strftime("%Y-%m-%d"),
        "TIME": now.strftime("%H:%M:%S"),
    }


def _read_messages_from_transcript(transcript_path):
    """Read messages from transcript file if it exists."""
    if not transcript_path:
        return []
    if not Path(transcript_path).exists():
        return []
    try:
        return _read_transcript_messages(Path(transcript_path).expanduser())
    except Exception:
        return []


def _get_message_variables(transcript_path):
    """Get MSG0-MSG9 variables from transcript."""
    messages = _read_messages_from_transcript(transcript_path)
    
    # Reverse so MSG0 is the latest message
    messages = list(reversed(messages))
    
    msg_vars = {}
    for i in range(10):  # MSG0 through MSG9
        msg_vars[f"MSG{i}"] = messages[i] if i < len(messages) else ""
    
    return msg_vars


def _get_template_variables(repo_name, branch_name, transcript_path=None):
    """Get all available template variables."""
    hostname, username, cwd, cwd_basename, tty = _get_system_info()
    
    variables = {
        "GIT_REPO": repo_name,
        "GIT_BRANCH": branch_name,
        "HOSTNAME": hostname,
        "USERNAME": username,
        "CWD": cwd,
        "CWD_BASENAME": cwd_basename,
        "TTY": tty,
    }
    
    # Add time variables
    variables.update(_get_time_variables())
    
    # Add message variables
    variables.update(_get_message_variables(transcript_path))

    return variables


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


def _log_stop_event_details(hook_data):
    """Log details about the stop event."""
    transcript_path = hook_data.get("transcript_path")
    logger.debug(f"Transcript path: {transcript_path}")
    logger.debug(f"Stop hook active: {hook_data.get('stop_hook_active')}")
    return transcript_path


def _log_config_details():
    """Log configuration details."""
    logger.debug(
        f"Config: num_messages={CONFIG['notification']['num_messages']}, "
        f"max_body_length={CONFIG['notification']['max_body_length']}"
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


if __name__ == "__main__":
    main()
