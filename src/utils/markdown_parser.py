"""Markdown parser utilities."""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MarkdownSection:
    """A section in a markdown document."""

    level: int  # Heading level (1-6)
    title: str
    content: str
    line_number: int
    children: list["MarkdownSection"] = field(default_factory=list)


@dataclass
class CheckboxItem:
    """A checkbox item in markdown."""

    text: str
    checked: bool
    line_number: int
    indent_level: int = 0


class MarkdownParser:
    """Parser for markdown documents."""

    # Patterns
    HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
    CHECKBOX_PATTERN = re.compile(r"^(\s*)[-*]\s*\[([ xX])\]\s*(.+)$")
    LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    CODE_BLOCK_START = re.compile(r"^```(\w*)$")
    CODE_BLOCK_END = re.compile(r"^```$")

    def __init__(self, content: str):
        self.content = content
        self.lines = content.split("\n")

    @classmethod
    def from_file(cls, path: Path) -> "MarkdownParser":
        """Create parser from a file."""
        content = path.read_text()
        return cls(content)

    def get_title(self) -> str | None:
        """Get the document title (first H1)."""
        for line in self.lines:
            match = self.HEADING_PATTERN.match(line)
            if match and len(match.group(1)) == 1:
                return match.group(2).strip()
        return None

    def get_sections(self, max_level: int = 6) -> list[MarkdownSection]:
        """Parse all sections up to a certain heading level."""
        sections = []
        current_section: MarkdownSection | None = None
        content_lines = []

        for line_num, line in enumerate(self.lines, start=1):
            match = self.HEADING_PATTERN.match(line)

            if match:
                level = len(match.group(1))
                title = match.group(2).strip()

                if level <= max_level:
                    # Save previous section
                    if current_section:
                        current_section.content = "\n".join(content_lines).strip()
                        sections.append(current_section)
                        content_lines = []

                    current_section = MarkdownSection(
                        level=level,
                        title=title,
                        content="",
                        line_number=line_num,
                    )
                else:
                    content_lines.append(line)
            else:
                content_lines.append(line)

        # Save last section
        if current_section:
            current_section.content = "\n".join(content_lines).strip()
            sections.append(current_section)

        return sections

    def get_checkboxes(self) -> list[CheckboxItem]:
        """Extract all checkbox items from the document."""
        checkboxes = []

        for line_num, line in enumerate(self.lines, start=1):
            match = self.CHECKBOX_PATTERN.match(line)
            if match:
                indent = len(match.group(1))
                checkbox_char = match.group(2)
                text = match.group(3).strip()

                checkboxes.append(CheckboxItem(
                    text=text,
                    checked=checkbox_char.lower() == "x",
                    line_number=line_num,
                    indent_level=indent // 2,  # Assuming 2-space indents
                ))

        return checkboxes

    def get_links(self) -> list[tuple[str, str]]:
        """Extract all links from the document.

        Returns list of (text, url) tuples.
        """
        links = []
        for line in self.lines:
            for match in self.LINK_PATTERN.finditer(line):
                links.append((match.group(1), match.group(2)))
        return links

    def get_code_blocks(self) -> list[tuple[str, str]]:
        """Extract all code blocks.

        Returns list of (language, code) tuples.
        """
        blocks = []
        in_block = False
        current_lang = ""
        current_code = []

        for line in self.lines:
            if not in_block:
                start_match = self.CODE_BLOCK_START.match(line)
                if start_match:
                    in_block = True
                    current_lang = start_match.group(1) or ""
                    current_code = []
            else:
                if self.CODE_BLOCK_END.match(line):
                    blocks.append((current_lang, "\n".join(current_code)))
                    in_block = False
                else:
                    current_code.append(line)

        return blocks

    def extract_section_content(self, section_title: str) -> str | None:
        """Extract content from a specific section by title."""
        sections = self.get_sections()

        for i, section in enumerate(sections):
            if section.title.lower() == section_title.lower():
                # Get content until next same-or-higher level heading
                content_lines = [section.content]

                # Include child sections
                for j in range(i + 1, len(sections)):
                    if sections[j].level <= section.level:
                        break
                    content_lines.append(f"{'#' * sections[j].level} {sections[j].title}")
                    content_lines.append(sections[j].content)

                return "\n\n".join(content_lines)

        return None

    def update_checkbox(self, line_number: int, checked: bool) -> str:
        """Update a checkbox at a specific line and return new content."""
        new_lines = list(self.lines)

        if 1 <= line_number <= len(new_lines):
            line = new_lines[line_number - 1]
            match = self.CHECKBOX_PATTERN.match(line)

            if match:
                indent = match.group(1)
                text = match.group(3)
                new_checkbox = "[x]" if checked else "[ ]"
                new_lines[line_number - 1] = f"{indent}- {new_checkbox} {text}"

        return "\n".join(new_lines)
