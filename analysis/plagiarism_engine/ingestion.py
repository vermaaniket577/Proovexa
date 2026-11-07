"""
Dynamic Document Ingestion & Text Extraction Engine.
===================================================
Supports PDF, DOCX, and TXT across academic and general domains.
Preserves character offsets, line numbers, paragraph indices, and page numbers.
"""

from __future__ import annotations
import os
import io
import re
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Tuple


@dataclass
class TokenSpan:
    """Represents an atomic token with document coordinates and normalization."""
    token_index: int       # 0-indexed sequential token position in document
    start_char: int        # Character start offset in document full_text
    end_char: int          # Character end offset in document full_text
    original_word: str     # Raw token string as extracted from source text
    normalized_word: str   # Normalized word (NFKC, lowercase, stripped ZWJ/ZWNJ)
    line_number: int = 1   # 1-indexed line number in document
    page_number: int = 1   # 1-indexed page number in document
    paragraph_index: int = 1  # 1-indexed paragraph number in document

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_index": self.token_index,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "original_word": self.original_word,
            "normalized_word": self.normalized_word,
            "line_number": self.line_number,
            "page_number": self.page_number,
            "paragraph_index": self.paragraph_index,
        }


@dataclass
class ParagraphSpan:
    """Represents a paragraph boundary with line and page numbers."""
    paragraph_index: int
    page_number: int
    start_char: int
    end_char: int
    text: str
    line_number: int = 1


@dataclass
class ParsedDocument:
    """Standardized ingested document payload preserving coordinates and metadata."""
    document_id: str
    filename: str
    file_type: str
    full_text: str
    char_count: int
    word_count: int
    page_count: int
    line_count: int
    paragraphs: List[ParagraphSpan] = field(default_factory=list)
    tokens: List[TokenSpan] = field(default_factory=list)
    language_detected: str = "en-IN"  # "en-IN", "hi-IN", or "mixed"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "char_count": self.char_count,
            "word_count": self.word_count,
            "page_count": self.page_count,
            "line_count": self.line_count,
            "language_detected": self.language_detected,
            "paragraph_count": len(self.paragraphs),
            "token_count": len(self.tokens),
            "metadata": self.metadata,
        }


class DocumentParser:
    """
    Dynamic Multi-Format Document Ingestion Engine.
    Handles .docx, .pdf, and .txt files, byte streams, and raw strings.
    """

    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.text', '.doc'}

    @classmethod
    def parse(
        cls,
        source: Union[str, Path, bytes, io.BytesIO],
        filename: Optional[str] = None,
        file_type: Optional[str] = None,
        document_id: Optional[str] = None
    ) -> ParsedDocument:
        """
        Main entry point for parsing any supported document format.
        """
        doc_id = document_id or f"trn:oid:::{uuid.uuid4().hex[:4]}:{int(uuid.uuid4().int % 10**9)}"

        # 1. Determine input type and filename
        if isinstance(source, (str, Path)):
            source_path = Path(source)
            if source_path.exists() and source_path.is_file():
                resolved_filename = filename or source_path.name
                ext = source_path.suffix.lower()
                with open(source_path, 'rb') as f:
                    content_bytes = f.read()
                return cls._parse_bytes(content_bytes, resolved_filename, ext, doc_id)
            elif isinstance(source, str) and not filename:
                # Direct string text passed
                return cls._parse_plain_text(source, filename or "document.txt", doc_id)

        if isinstance(source, (bytes, bytearray)):
            resolved_filename = filename or "document.txt"
            ext = (file_type or Path(resolved_filename).suffix).lower()
            if not ext.startswith('.'):
                ext = f".{ext}"
            return cls._parse_bytes(bytes(source), resolved_filename, ext, doc_id)

        if isinstance(source, io.BytesIO):
            resolved_filename = filename or "document.txt"
            ext = (file_type or Path(resolved_filename).suffix).lower()
            if not ext.startswith('.'):
                ext = f".{ext}"
            return cls._parse_bytes(source.getvalue(), resolved_filename, ext, doc_id)

        # Fallback to plain text representation
        return cls._parse_plain_text(str(source), filename or "document.txt", doc_id)

    @classmethod
    def _parse_bytes(cls, data: bytes, filename: str, ext: str, doc_id: str) -> ParsedDocument:
        """Route byte stream to appropriate format extractor."""
        if ext == '.pdf':
            return cls._parse_pdf_bytes(data, filename, doc_id)
        elif ext in ('.docx', '.doc'):
            return cls._parse_docx_bytes(data, filename, doc_id)
        else:
            # Universal text auto-detection
            text = cls._decode_text_bytes(data)
            return cls._parse_plain_text(text, filename, doc_id)

    # -------------------------------------------------------------------------
    # PDF Parser (PyMuPDF Layout-Aware Stream Ordering)
    # -------------------------------------------------------------------------
    @classmethod
    def _parse_pdf_bytes(cls, data: bytes, filename: str, doc_id: str) -> ParsedDocument:
        """
        Extract text from PDF using PyMuPDF (fitz) with layout-aware block ordering.
        Preserves page numbers, paragraph structures, bounding blocks, and character offsets.
        """
        import fitz  # PyMuPDF

        doc = fitz.open(stream=data, filetype="pdf")
        paragraphs: List[ParagraphSpan] = []
        full_text_parts: List[str] = []
        char_cursor = 0
        line_cursor = 1
        para_idx = 1
        page_count = len(doc)

        for page_num in range(1, page_count + 1):
            page = doc.load_page(page_num - 1)
            # get_text("blocks"): returns list of (x0, y0, x1, y1, "text", block_no, block_type)
            # block_type == 0 is text block, 1 is image
            blocks = page.get_text("blocks")
            # Sort blocks top-to-bottom, left-to-right (layout-aware natural reading order)
            blocks.sort(key=lambda b: (round(b[1], 1), round(b[0], 1)))

            for b in blocks:
                if len(b) >= 7 and b[6] != 0:
                    continue  # Skip image blocks
                block_text = b[4].strip()
                if not block_text:
                    continue

                # Normalize intra-paragraph newlines into spaces unless empty line
                lines = [l.strip() for l in block_text.split('\n') if l.strip()]
                clean_para_text = " ".join(lines)
                if not clean_para_text:
                    continue

                if full_text_parts:
                    full_text_parts.append("\n\n")
                    char_cursor += 2
                    line_cursor += 1

                start_char = char_cursor
                full_text_parts.append(clean_para_text)
                end_char = start_char + len(clean_para_text)
                char_cursor = end_char

                para_lines = max(1, len(lines))
                paragraphs.append(ParagraphSpan(
                    paragraph_index=para_idx,
                    page_number=page_num,
                    start_char=start_char,
                    end_char=end_char,
                    text=clean_para_text,
                    line_number=line_cursor
                ))
                para_idx += 1
                line_cursor += para_lines

        doc.close()
        full_text = "".join(full_text_parts)
        line_count = full_text.count('\n') + 1

        return cls._build_parsed_document(
            doc_id=doc_id,
            filename=filename,
            file_type="pdf",
            full_text=full_text,
            paragraphs=paragraphs,
            page_count=max(1, page_count),
            line_count=line_count
        )

    # -------------------------------------------------------------------------
    # DOCX Parser (Paragraphs + Table Cells + Page Break Detection)
    # -------------------------------------------------------------------------
    @classmethod
    def _parse_docx_bytes(cls, data: bytes, filename: str, doc_id: str) -> ParsedDocument:
        """
        Extract text from DOCX using python-docx.
        Preserves paragraphs, table cells in natural sequence order, and page breaks.
        """
        from docx import Document as DocxDocument
        from docx.text.paragraph import Paragraph
        from docx.table import Table
        from docx.oxml.ns import qn

        docx_file = io.BytesIO(data)
        doc = DocxDocument(docx_file)

        paragraphs: List[ParagraphSpan] = []
        full_text_parts: List[str] = []
        char_cursor = 0
        line_cursor = 1
        para_idx = 1
        page_num = 1

        # Traverse document body elements in XML sequence order (interleaved paragraphs & tables)
        for element in doc.element.body:
            tag = element.tag.lower()
            if tag.endswith('p'):
                p_obj = Paragraph(element, doc)
                p_text = p_obj.text.strip() if p_obj.text else ""

                # Check runs in element for page breaks
                has_page_break = False
                for br in element.iter(qn('w:br')):
                    if br.get(qn('w:type')) == 'page':
                        has_page_break = True
                if element.find(qn('w:lastRenderedPageBreak')) is not None:
                    has_page_break = True

                if has_page_break:
                    page_num += 1

                if not p_text:
                    continue

                clean_text = re.sub(r'\s+', ' ', p_text).strip()
                if not clean_text:
                    continue

                if full_text_parts:
                    full_text_parts.append("\n\n")
                    char_cursor += 2
                    line_cursor += 1

                start_char = char_cursor
                full_text_parts.append(clean_text)
                end_char = start_char + len(clean_text)
                char_cursor = end_char

                paragraphs.append(ParagraphSpan(
                    paragraph_index=para_idx,
                    page_number=page_num,
                    start_char=start_char,
                    end_char=end_char,
                    text=clean_text,
                    line_number=line_cursor
                ))
                para_idx += 1
                line_cursor += 1

            elif tag.endswith('tbl'):
                # Table element: extract cells row-by-row
                table_obj = Table(element, doc)
                for row in table_obj.rows:
                    row_cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if row_cells:
                        row_line = " | ".join(row_cells)
                        if full_text_parts:
                            full_text_parts.append("\n")
                            char_cursor += 1
                            line_cursor += 1

                        start_char = char_cursor
                        full_text_parts.append(row_line)
                        end_char = start_char + len(row_line)
                        char_cursor = end_char

                        paragraphs.append(ParagraphSpan(
                            paragraph_index=para_idx,
                            page_number=page_num,
                            start_char=start_char,
                            end_char=end_char,
                            text=row_line,
                            line_number=line_cursor
                        ))
                        para_idx += 1
                        line_cursor += 1

        full_text = "".join(full_text_parts)
        line_count = full_text.count('\n') + 1

        return cls._build_parsed_document(
            doc_id=doc_id,
            filename=filename,
            file_type="docx",
            full_text=full_text,
            paragraphs=paragraphs,
            page_count=max(1, page_num),
            line_count=line_count
        )

    # -------------------------------------------------------------------------
    # TXT Parser (Universal Encoding Auto-Detection)
    # -------------------------------------------------------------------------
    @classmethod
    def _decode_text_bytes(cls, data: bytes) -> str:
        """Universal text auto-detection trying UTF-8, UTF-8-SIG, UTF-16, ISO-8859-1, CP1252."""
        encodings = [
            'utf-8',
            'utf-8-sig',
            'utf-16',
            'utf-16-le',
            'utf-16-be',
            'iso-8859-1',
            'cp1252',
            'latin-1'
        ]
        for enc in encodings:
            try:
                decoded = data.decode(enc)
                return decoded
            except (UnicodeDecodeError, LookupError):
                continue
        # Fallback with replacement
        return data.decode('utf-8', errors='replace')

    @classmethod
    def _parse_plain_text(cls, text: str, filename: str, doc_id: str) -> ParsedDocument:
        """Parse raw plain text into structured paragraphs and lines."""
        # Normalize carriage returns
        norm_text = text.replace('\r\n', '\n').replace('\r', '\n')
        raw_paras = re.split(r'\n\s*\n', norm_text)

        paragraphs: List[ParagraphSpan] = []
        full_text_parts: List[str] = []
        char_cursor = 0
        line_cursor = 1
        para_idx = 1
        page_num = 1

        for p in raw_paras:
            clean = p.strip()
            if not clean:
                line_cursor += p.count('\n') + 2
                continue

            # Standard 500 words per page approximation for unpaginated text
            if len(" ".join(full_text_parts).split()) // 500 + 1 > page_num:
                page_num += 1

            if full_text_parts:
                full_text_parts.append("\n\n")
                char_cursor += 2
                line_cursor += 1

            start_char = char_cursor
            full_text_parts.append(clean)
            end_char = start_char + len(clean)
            char_cursor = end_char

            p_lines = max(1, clean.count('\n') + 1)
            paragraphs.append(ParagraphSpan(
                paragraph_index=para_idx,
                page_number=page_num,
                start_char=start_char,
                end_char=end_char,
                text=clean,
                line_number=line_cursor
            ))
            para_idx += 1
            line_cursor += p_lines

        full_text = "".join(full_text_parts)
        line_count = full_text.count('\n') + 1

        return cls._build_parsed_document(
            doc_id=doc_id,
            filename=filename,
            file_type="txt",
            full_text=full_text,
            paragraphs=paragraphs,
            page_count=max(1, page_num),
            line_count=line_count
        )

    # -------------------------------------------------------------------------
    # Helper to assemble ParsedDocument and generate TokenSpans
    # -------------------------------------------------------------------------
    @classmethod
    def _build_parsed_document(
        cls,
        doc_id: str,
        filename: str,
        file_type: str,
        full_text: str,
        paragraphs: List[ParagraphSpan],
        page_count: int,
        line_count: int
    ) -> ParsedDocument:
        """Constructs TokenSpans and language detection."""
        from .preprocessor import BilingualPreprocessor

        preprocessor = BilingualPreprocessor()
        tokens = preprocessor.tokenize_with_offsets(full_text, paragraphs=paragraphs)
        lang = preprocessor.detect_language(full_text)

        word_count = len(tokens)
        char_count = len(full_text)

        return ParsedDocument(
            document_id=doc_id,
            filename=filename,
            file_type=file_type,
            full_text=full_text,
            char_count=char_count,
            word_count=word_count,
            page_count=page_count,
            line_count=line_count,
            paragraphs=paragraphs,
            tokens=tokens,
            language_detected=lang,
            metadata={"source_format": file_type}
        )
