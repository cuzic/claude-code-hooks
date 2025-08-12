"""
Claude Code hook for sending Pushbullet notifications when tasks complete.
Reads JSON from stdin and processes transcript files.
"""

# Import modules that tests need to patch
from datetime import datetime
import subprocess
import os
import socket
import logging

# Import configuration first
from .config import (
    CONFIG,
    DEFAULT_NUM_MESSAGES,
    DEFAULT_MAX_BODY_LENGTH,
    DEFAULT_SPLIT_LONG_MESSAGES,
    load_config,
    merge_configs,
    setup_logging,
)

# Import transcript processing functions
from .transcript import (
    read_hook_input,
    get_last_messages_from_transcript,
    _extract_text_from_list,
    _extract_message_text,
    _is_assistant_message,
    _parse_json_line,
    _process_transcript_line,
    _read_transcript_messages,
    _read_messages_from_transcript,
    _calculate_effective_max_length,
    _should_add_overlap,
    _split_by_sentences,
    _split_by_characters,
    _split_by_words,
    _handle_paragraph_overlap,
    _process_paragraph,
    _split_message_into_chunks,
    _add_part_numbers_to_title,
    _format_notification_body,
)

# Import template processing functions
from .template import (
    get_git_info,
    _get_git_info_from_env,
    _get_repo_name_from_git,
    _get_branch_name_from_git,
    _get_tty_direct,
    _get_tty_for_pid,
    _get_parent_pid_from_proc,
    _get_tty_from_parent_processes,
    _get_system_info,
    _get_time_variables,
    _get_message_variables,
    _resolve_variable_content,
    _remove_quotes,
    _truncate_text,
    _apply_truncate_function,
    _apply_substr_function,
    _extract_substr_params,
    _process_substr_match,
    _find_function_bounds,
    _apply_complex_substr,
    _extract_regex_params,
    _apply_regex_pattern,
    _process_regex_match,
    _apply_regex_function,
    _apply_string_functions,
    _format_template,
    _get_template_variables,
)

# Import Pushbullet and main functions
from .pushbullet import (
    send_pushbullet_notification,
    send_split_notifications,
    _get_pushbullet_token,
    _send_via_requests,
    _send_via_curl,
    _get_split_config,
    _calculate_reserve_space,
    _send_single_chunk,
    _send_numbered_chunk,
    _apply_notification_delay,
    _send_notification,
    _handle_test_mode,
    _log_stop_event_details,
    _log_config_details,
    _handle_stop_event,
    _handle_hook_mode,
    _handle_legacy_mode,
    main,
)

# Re-export public API for backward compatibility
__all__ = [
    # Configuration
    "CONFIG",
    "DEFAULT_NUM_MESSAGES",
    "DEFAULT_MAX_BODY_LENGTH", 
    "DEFAULT_SPLIT_LONG_MESSAGES",
    "load_config",
    "merge_configs",
    "setup_logging",
    
    # Main functions
    "main",
    "read_hook_input",
    "get_git_info",
    "get_last_messages_from_transcript",
    "send_pushbullet_notification",
    "send_split_notifications",
    
    # Template functions (for testing)
    "_format_template",
    "_get_template_variables",
    "_apply_string_functions",
    "_apply_truncate_function",
    "_apply_substr_function", 
    "_apply_regex_function",
    
    # Message splitting (for testing)
    "_split_message_into_chunks",
    "_add_part_numbers_to_title",
    
    # Internal functions (for testing compatibility)
    "_extract_text_from_list",
    "_extract_message_text",
    "_is_assistant_message",
    "_parse_json_line",
    "_process_transcript_line",
    "_read_transcript_messages",
    "_read_messages_from_transcript",
    "_calculate_effective_max_length",
    "_should_add_overlap",
    "_split_by_sentences",
    "_split_by_characters", 
    "_split_by_words",
    "_handle_paragraph_overlap",
    "_process_paragraph",
    "_format_notification_body",
    "_get_git_info_from_env",
    "_get_repo_name_from_git",
    "_get_branch_name_from_git",
    "_get_tty_direct",
    "_get_tty_for_pid",
    "_get_parent_pid_from_proc", 
    "_get_tty_from_parent_processes",
    "_get_system_info",
    "_get_time_variables",
    "_get_message_variables",
    "_resolve_variable_content",
    "_remove_quotes",
    "_truncate_text",
    "_extract_substr_params",
    "_process_substr_match", 
    "_find_function_bounds",
    "_apply_complex_substr",
    "_extract_regex_params",
    "_apply_regex_pattern",
    "_process_regex_match",
    "_get_pushbullet_token",
    "_send_via_requests",
    "_send_via_curl",
    "_get_split_config",
    "_calculate_reserve_space",
    "_send_single_chunk", 
    "_send_numbered_chunk",
    "_apply_notification_delay",
    "_send_notification",
    "_handle_test_mode",
    "_log_stop_event_details",
    "_log_config_details",
    "_handle_stop_event",
    "_handle_hook_mode",
    "_handle_legacy_mode",
]

if __name__ == "__main__":
    main()