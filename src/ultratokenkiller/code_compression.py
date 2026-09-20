"""Syntax-aware summaries built with general-purpose tree-sitter grammars."""
import re
from functools import lru_cache

LANGUAGES = {"javascript", "typescript", "tsx", "go", "rust", "java", "c", "cpp", "perl"}
FUNCTIONS = {"function_declaration", "function_definition", "method_definition", "method_declaration",
             "function_item", "constructor_declaration", "arrow_function", "function_expression",
             "subroutine_declaration_statement", "subroutine_definition"}
BLOCKS = {"statement_block", "block", "compound_statement", "constructor_body"}


@lru_cache(maxsize=16)
def parser_for(language):
    from tree_sitter_language_pack import get_parser
    if language not in LANGUAGES:
        raise ValueError("Unsupported source language")
    return get_parser(language)


def summarize_code(text: str, language: str, query: str = "") -> str:
    parser = parser_for(language)
    source = text.encode("utf-8")
    tree = parser.parse(source)
    if tree.root_node.has_error:
        return text
    edits = []
    def visit(node):
        if node.type in FUNCTIONS:
            name = node.child_by_field_name("name")
            if name is not None:
                identifier = source[name.start_byte:name.end_byte].decode("utf-8", errors="ignore")
                signature_only = bool(
                    re.search(r"\b(signature|declaration|prototype|type|api)\b", query, re.I)
                )
                if identifier and identifier in query and not signature_only:
                    return
            body = node.child_by_field_name("body")
            if body is None:
                body = next((child for child in node.named_children if child.type in BLOCKS), None)
            if body is not None and body.type in BLOCKS and body.end_byte-body.start_byte > 160:
                replacement = b"{ /* UTK: original body available through recovery */ }"
                if language == "perl":
                    replacement = b"{ # UTK: original body available through recovery\n }"
                edits.append((body.start_byte, body.end_byte, replacement))
                return
        for child in node.named_children:
            visit(child)
    visit(tree.root_node)
    for start, end, replacement in reversed(edits):
        source = source[:start]+replacement+source[end:]
    if parser.parse(source).root_node.has_error:
        return text
    return source.decode("utf-8")
