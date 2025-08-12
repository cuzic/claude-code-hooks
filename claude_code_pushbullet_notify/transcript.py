"""Transcript processing and message handling for Claude Code notifications."""

import json
import logging
import sys
from pathlib import Path

from .config import CONFIG

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


# Message splitting functions

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
    if max_length and not CONFIG.get("notification", {}).get("split_long_messages", True):
        if len(result) > max_length:
            result = result[: max_length - 3] + "..."

    return result


def get_last_messages_from_transcript(transcript_path, num_lines=None):
    """Get the last N lines from the transcript file."""
    if not transcript_path or not Path(transcript_path).exists():
        return "completed."

    # Use config values if not specified
    if num_lines is None:
        num_lines = CONFIG.get("notification", {}).get("num_messages", 3)

    try:
        transcript_path = Path(transcript_path).expanduser()
        messages = _read_transcript_messages(transcript_path)
        # Don't pass max_length anymore as splitting is handled during sending
        return _format_notification_body(messages, num_lines)
    except Exception as e:
        logger.error(f"Error reading transcript: {e}")
        return "Task completed."