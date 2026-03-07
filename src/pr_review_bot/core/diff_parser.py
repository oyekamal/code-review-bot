"""Diff parsing utilities."""
import re
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class DiffParser:
    """Parse unified diff format to extract file changes and line numbers."""
    
    def __init__(self, diff: str):
        """Initialize with diff content.
        
        Args:
            diff: Unified diff string
        """
        self.diff = diff
        self.files = self._parse_files()
    
    def _parse_files(self) -> Dict[str, List[Tuple[int, str]]]:
        """Parse diff into files with their changed lines.
        
        Returns:
            Dict mapping file paths to list of (line_number, line_content) tuples
        """
        files = {}
        current_file = None
        current_line = 0
        
        for line in self.diff.split('\n'):
            # New file
            if line.startswith('diff --git'):
                continue
            elif line.startswith('+++'):
                # Extract file path
                match = re.match(r'\+\+\+ b/(.+)', line)
                if match:
                    current_file = match.group(1)
                    files[current_file] = []
            # Hunk header: @@ -old_start,old_count +new_start,new_count @@
            elif line.startswith('@@'):
                match = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
                if match:
                    current_line = int(match.group(1))
            # Added or context line
            elif current_file is not None:
                if line.startswith('+') and not line.startswith('+++'):
                    # Added line
                    files[current_file].append((current_line, line[1:]))
                    current_line += 1
                elif line.startswith(' '):
                    # Context line (unchanged but visible in diff — valid comment target)
                    files[current_file].append((current_line, line[1:]))
                    current_line += 1
                # Deleted lines (starting with '-') don't increment new line number
        
        return files
    
    def get_valid_lines_for_file(self, file_path: str) -> List[int]:
        """Get list of valid line numbers for a file (lines that were added or changed).
        
        Args:
            file_path: File path to check
            
        Returns:
            List of valid line numbers
        """
        if file_path not in self.files:
            return []
        
        return [line_num for line_num, _ in self.files[file_path]]
    
    def validate_comment(self, file_path: str, line_number: int) -> bool:
        """Validate if a comment line number is valid for the file.
        
        Args:
            file_path: File path
            line_number: Line number to validate
            
        Returns:
            True if valid, False otherwise
        """
        valid_lines = self.get_valid_lines_for_file(file_path)
        return line_number in valid_lines or (
            # Allow nearby lines (within 5 lines of a change)
            any(abs(line_number - valid_line) <= 5 for valid_line in valid_lines)
        )
    
    def get_file_summary(self) -> Dict[str, int]:
        """Get summary of changes per file.
        
        Returns:
            Dict mapping file paths to number of changed lines
        """
        return {
            file_path: len(lines)
            for file_path, lines in self.files.items()
        }
    
    def get_changed_content(self, file_path: str, max_lines: int = 50) -> str:
        """Get the changed content for a file.
        
        Args:
            file_path: File path
            max_lines: Maximum lines to return
            
        Returns:
            String of changed lines
        """
        if file_path not in self.files:
            return ""
        
        lines = self.files[file_path][:max_lines]
        content = []
        
        for line_num, line_content in lines:
            content.append(f"{line_num}: {line_content}")
        
        if len(self.files[file_path]) > max_lines:
            content.append(f"... and {len(self.files[file_path]) - max_lines} more lines")
        
        return '\n'.join(content)
    
    def get_file_diff(self, file_path: str) -> str:
        """Extract the diff for a specific file.
        
        Args:
            file_path: File path to extract
            
        Returns:
            Diff string for just that file
        """
        lines = []
        in_target_file = False
        current_file = None
        
        for line in self.diff.split('\n'):
            # Track which file we're in
            if line.startswith('diff --git'):
                # Check if this is our target file
                if f' b/{file_path}' in line:
                    in_target_file = True
                    current_file = file_path
                    lines.append(line)
                else:
                    # Moved to a different file
                    if in_target_file:
                        break
                    in_target_file = False
            elif in_target_file:
                lines.append(line)
        
        return '\n'.join(lines)
    
    def split_by_files(self) -> Dict[str, str]:
        """Split the full diff into per-file diffs.
        
        Returns:
            Dict mapping file paths to their individual diffs
        """
        file_diffs = {}
        current_file = None
        current_diff_lines = []
        
        for line in self.diff.split('\n'):
            if line.startswith('diff --git'):
                # Save previous file's diff
                if current_file and current_diff_lines:
                    file_diffs[current_file] = '\n'.join(current_diff_lines)
                    current_diff_lines = []
                
                # Extract new file path
                match = re.search(r'b/(.+)$', line)
                if match:
                    current_file = match.group(1)
                    current_diff_lines.append(line)
            else:
                if current_file:
                    current_diff_lines.append(line)
        
        # Save last file
        if current_file and current_diff_lines:
            file_diffs[current_file] = '\n'.join(current_diff_lines)
        
        return file_diffs
