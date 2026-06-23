from __future__ import annotations

from folio.core.cleaner import clean_markdown


class TestBase64ImageStripping:
    def test_strips_png_base64_image(self):
        text = "Before\n![Image](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)\nAfter"
        result = clean_markdown(text)
        assert "![Image](data:image" not in result
        assert "Before" in result
        assert "After" in result

    def test_strips_jpeg_base64_image(self):
        text = "![Image](data:image/jpeg;base64,/9j/4AAQSkZJRg==)"
        result = clean_markdown(text)
        assert "data:image" not in result

    def test_strips_gif_base64_image(self):
        text = "![Image](data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7)"
        result = clean_markdown(text)
        assert "data:image" not in result

    def test_placeholder_becomes_image_tag_then_removed(self):
        text = "![Image](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)"
        result = clean_markdown(text)
        assert "[IMAGE]" not in result


class TestWhitespaceNormalization:
    def test_collapses_multiple_blank_lines_to_one(self):
        text = "Line 1\n\n\n\nLine 2"
        result = clean_markdown(text)
        assert "\n\n\n\n" not in result
        assert result.count("\n\n") == 1

    def test_collapses_three_blank_lines(self):
        text = "Hello\n\n\nWorld"
        result = clean_markdown(text)
        assert result.count("\n\n") == 1
        assert "Hello" in result
        assert "World" in result

    def test_converts_crlf_to_lf(self):
        text = "Line 1\r\nLine 2\r\n\r\nLine 3"
        result = clean_markdown(text)
        assert "\r\n" not in result
        assert "\r" not in result

    def test_converts_tabs_to_spaces(self):
        text = "col1\tcol2\tcol3"
        result = clean_markdown(text)
        assert "\t" not in result

    def test_collapses_multiple_spaces_to_one(self):
        text = "word1    word2     word3"
        result = clean_markdown(text)
        assert "    " not in result
        assert "word1 word2 word3" in result

    def test_strips_trailing_whitespace_on_final_line(self):
        text = "Hello   "
        result = clean_markdown(text)
        assert result == "Hello\n"


class TestFormChromeRemoval:
    def test_removes_writing_tip_heading(self):
        text = "## Writing tip\n\nSome content"
        result = clean_markdown(text)
        assert "Writing tip" not in result
        assert "Some content" in result

    def test_removes_upload_pdf_heading(self):
        text = "### Upload the PDF file\n\nBody text"
        result = clean_markdown(text)
        assert "Upload" not in result
        assert "Body text" in result

    def test_removes_mandatory_heading(self):
        text = "## (mandatory)\n\nBody"
        result = clean_markdown(text)
        assert "(mandatory)" not in result
        assert "Body" in result

    def test_removes_for_office_use_only_heading(self):
        text = "# FOR OFFICE USE ONLY\n\nContent"
        result = clean_markdown(text)
        assert "FOR OFFICE USE ONLY" not in result
        assert "Content" in result

    def test_removes_protected_b_heading(self):
        text = "### Protected B when completed\n\nText"
        result = clean_markdown(text)
        assert "Protected" not in result
        assert "Text" in result

    def test_removes_please_note_heading(self):
        text = "### Please note the following\n\nContent"
        result = clean_markdown(text)
        assert "Please note" not in result
        assert "Content" in result

    def test_removes_to_enter_heading(self):
        text = "### To enter your information\n\nData"
        result = clean_markdown(text)
        assert "To enter" not in result
        assert "Data" in result

    def test_removes_application_preview_heading(self):
        text = "## Application Preview\n\nDetails"
        result = clean_markdown(text)
        assert "Application Preview" not in result
        assert "Details" in result

    def test_removes_voluntary_self_id_heading(self):
        text = "## Voluntary Self-Identification\n\nForm"
        result = clean_markdown(text)
        assert "Voluntary Self" not in result
        assert "Form" in result

    def test_removes_form_label_with_value_email(self):
        text = "Email:\nfoo@example.com\n\nContent"
        result = clean_markdown(text)
        assert "Email:" not in result
        assert "foo@example.com" not in result
        assert "Content" in result

    def test_removes_form_label_with_value_url(self):
        text = "Website:\nhttps://example.com\n\nBody"
        result = clean_markdown(text)
        assert "Website:" not in result
        assert "example.com" not in result
        assert "Body" in result

    def test_removes_form_label_organization(self):
        text = "Organization:\nSome Org\n\nBody"
        result = clean_markdown(text)
        assert "Organization:" not in result

    def test_removes_form_label_postal_code(self):
        text = "Postal Code:\nM5A 1B2\n\nContent"
        result = clean_markdown(text)
        assert "Postal Code:" not in result
        assert "M5A 1B2" not in result

    def test_removes_form_label_standalone(self):
        text = "Address:\n\nBody"
        result = clean_markdown(text)
        assert "Address:" not in result
        assert "Body" in result

    def test_removes_checkbox_widgets(self):
        text = "[] Option A\n[x] Option B\n[ ] Option C\n[X] Option D"
        result = clean_markdown(text)
        assert "Option A" in result
        assert "Option B" in result
        assert "[ ]" not in result
        assert "[x]" not in result

    def test_removes_unicode_checkboxes(self):
        text = "\u2610 Item 1\n\u2611 Item 2"
        result = clean_markdown(text)
        assert "\u2610" not in result
        assert "\u2611" not in result

    def test_removes_file_metadata_line(self):
        text = "Total Files: 12\n\nContent"
        result = clean_markdown(text)
        assert "Total Files" not in result

    def test_removes_file_metadata_line_singular(self):
        text = "Total File: 1\n\nContent"
        result = clean_markdown(text)
        assert "Total File" not in result

    def test_form_chrome_disabled_with_empty_list(self):
        text = "## Writing tip\n\nContent"
        result = clean_markdown(text, config={"form_chrome_patterns": []})
        assert "Writing tip" in result


class TestHtmlEntityDecode:
    def test_decodes_decimal_numeric_entity(self):
        text = "She said &#39;hello&#39;"
        result = clean_markdown(text)
        assert "'hello'" in result
        assert "&#39;" not in result

    def test_decodes_hex_numeric_entity(self):
        text = "She said &#x27;hello&#x27;"
        result = clean_markdown(text)
        assert "'hello'" in result
        assert "&#x27;" not in result

    def test_decodes_multiple_numeric_entities(self):
        text = "&#65;&#66;&#67;"
        result = clean_markdown(text)
        assert "ABC" in result

    def test_named_entity_ampersand_not_decoded(self):
        text = "A &amp; B"
        result = clean_markdown(text)
        assert "&amp;" in result

    def test_named_entity_lt_not_decoded(self):
        text = "x &lt; y"
        result = clean_markdown(text)
        assert "&lt;" in result

    def test_named_entity_gt_not_decoded(self):
        text = "x &gt; y"
        result = clean_markdown(text)
        assert "&gt;" in result

    def test_named_entity_quot_not_decoded(self):
        text = "&quot;hello&quot;"
        result = clean_markdown(text)
        assert "&quot;" in result

    def test_nbsp_not_decoded_as_entity(self):
        text = "hello&nbsp;world"
        result = clean_markdown(text)
        assert "&nbsp;" in result

    def test_zero_width_space_removed(self):
        text = "hello\u200Bworld"
        result = clean_markdown(text)
        assert "helloworld" in result
        assert "\u200B" not in result

    def test_non_breaking_space_unicode_replaced_with_space(self):
        text = "hello\u00A0world"
        result = clean_markdown(text)
        assert "hello world" in result
        assert "\u00A0" not in result

    def test_bom_removed(self):
        text = "\uFEFFhello"
        result = clean_markdown(text)
        assert result.startswith("hello")

    def test_html_entity_decode_disabled(self):
        text = "&#39;test&#39;"
        result = clean_markdown(text, config={"corruption_fixes": {"html_entities": False}})
        assert "&#39;" in result


class TestCorruptionFix:
    def test_removes_single_alpha_char_line_between_blank_lines(self):
        text = "Content\n\na\n\nMore content"
        result = clean_markdown(text)
        assert "\na\n" not in result

    def test_removes_bare_digit_line_surrounded_by_blanks(self):
        text = "Content\n\n42\n\nMore content"
        result = clean_markdown(text)
        assert "\n42\n" not in result

    def test_rejoins_split_words(self):
        text = "he llo wor ld"
        result = clean_markdown(text)
        assert "hello" in result
        assert "world" in result

    def test_keeps_bare_digit_in_context(self):
        text = "Line with 42 in context"
        result = clean_markdown(text)
        assert "42" in result

    def test_single_char_line_removal_disabled(self):
        text = "Content\n\na\n\nMore content"
        result = clean_markdown(text, config={"corruption_fixes": {"single_char_lines": False}})
        assert "\na\n" in result

    def test_split_word_rejoin_disabled(self):
        text = "The qu ick fox"
        result = clean_markdown(text, config={"corruption_fixes": {"split_words": False}})
        assert "qu ick" in result

    def test_corruption_fixes_bool_false_disables_all(self):
        text = "&#39;test&#39;\n\na\n\nMore"
        result = clean_markdown(text, config={"corruption_fixes": False})
        assert "&#39;" in result
        assert "\na\n" in result


class TestBoldToHeadingConversion:
    def test_converts_standalone_bold_to_heading(self):
        text = "Before\n\n**My Title**\n\nAfter"
        result = clean_markdown(text)
        assert "### My Title" in result

    def test_does_not_convert_inline_bold(self):
        text = "This is **bold text** in a sentence"
        result = clean_markdown(text)
        assert "### bold text" not in result

    def test_does_not_convert_bold_without_blank_lines(self):
        text = "Not blank above\n**My Title**\nNot blank below"
        result = clean_markdown(text)
        assert "### My Title" not in result

    def test_converts_bold_at_start_of_document(self):
        text = "**Title at Start**\n\nBody"
        result = clean_markdown(text)
        assert "### Title at Start" in result

    def test_converts_bold_at_end_of_document(self):
        text = "Body\n\n**Project Summary**"
        result = clean_markdown(text)
        assert "### Project Summary" in result

    def test_does_not_convert_long_bold_text(self):
        title = "X" * 100
        text = f"\n\n**{title}**\n\nbody"
        result = clean_markdown(text)
        assert "### " + title not in result

    def test_strips_inner_whitespace_in_bold_heading(self):
        text = "\n\n**  Spaced Title  **\n\nBody"
        result = clean_markdown(text)
        assert "### Spaced Title" in result


class TestHeadingNormalization:
    def test_title_cases_all_caps_heading(self):
        text = "# THIS IS A HEADING"
        result = clean_markdown(text)
        assert "This Isa" in result
        assert "Heading" in result

    def test_lowercases_small_words_in_heading(self):
        text = "# GRANTS AND OPERATING SUPPORT"
        result = clean_markdown(text)
        assert "and" in result
        assert "Grants" in result

    def test_leaves_mixed_case_heading(self):
        text = "# My Normal Heading"
        result = clean_markdown(text)
        assert "My Normal Heading" in result

    def test_does_not_normalize_non_alpha_heavy_heading(self):
        text = "# 2024 Q1 Report"
        result = clean_markdown(text)
        assert "2024 Q1 Report" in result


class TestUselessHeadingRemoval:
    def test_removes_heading_matching_custom_pattern(self):
        text = "## Delete Me\n\nBody"
        result = clean_markdown(text, config={"useless_headings": [r"^#{1,6}\s+Delete\s+Me"]})
        assert "Delete Me" not in result
        assert "Body" in result

    def test_keeps_unmatched_headings(self):
        text = "## Keep Me\n\nBody"
        result = clean_markdown(text, config={"useless_headings": [r"^#{1,6}\s+Delete\s+Me"]})
        assert "Keep Me" in result

    def test_no_useless_headings_by_default(self):
        text = "## Regular Heading\n\nBody"
        result = clean_markdown(text)
        assert "Regular Heading" in result


class TestMaxPassesGuard:
    def test_clean_markdown_terminates_with_many_triggers(self):
        text = "![Image](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)\n\n\n\nx\n\n\na\n\n&#65;\n\n\n\n**Title**\n\n# WRITING TIP\n\n?  What is the meaning of life, the universe, and everything? It's forty-two.\n\n## Application Preview\n\nBody"
        result = clean_markdown(text)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_input_terminates(self):
        result = clean_markdown("")
        assert isinstance(result, str)

    def test_whitespace_only_terminates(self):
        result = clean_markdown("   \n\n\n   \t  ")
        assert isinstance(result, str)


class TestConfigDrivenBehavior:
    def test_corruption_fixes_bool_true_enables_all(self):
        text = "&#39;test&#39;\n\na\n\nMore"
        result = clean_markdown(text, config={"corruption_fixes": True})
        assert "&#39;" not in result
        assert "\na\n" not in result

    def test_custom_form_chrome_patterns(self):
        text = "# Custom Bad Heading\n\nBody"
        result = clean_markdown(text, config={"form_chrome_patterns": [r"^#{1,6}\s+Custom\s+Bad"]})
        assert "Custom Bad Heading" not in result

    def test_custom_form_chrome_supplements_defaults_only_when_provided(self):
        text = "## Writing tip\n\n# Custom Bad\n\nBody"
        result = clean_markdown(
            text,
            config={"form_chrome_patterns": [r"^#{1,6}\s+Custom\s+Bad"]},
        )
        assert "Writing tip" in result
        assert "Custom Bad" not in result

    def test_sub_key_off_while_others_on(self):
        text = "&#39;\n\na\n\nMore"
        result = clean_markdown(
            text,
            config={
                "corruption_fixes": {
                    "html_entities": True,
                    "single_char_lines": False,
                    "split_words": True,
                }
            },
        )
        assert "&#39;" not in result
        assert "\na\n" in result


class TestAdditionalPasses:
    def test_italicizes_writing_tip_line(self):
        text = "Writing tip: Make it clear"
        result = clean_markdown(text)
        assert "*Writing tip: Make it clear*" in result

    def test_splits_question_answer_on_same_line(self):
        text = "What is the purpose of this grant? The purpose of this grant is to support artistic excellence."
        result = clean_markdown(text)
        assert result.startswith("### What isthe purpose of this grant\n")
        assert "artistic excellence" in result

    def test_extracts_parenthetical_from_heading(self):
        text = "## My Heading (important note)\n\nBody"
        result = clean_markdown(text)
        assert "## My Heading" in result
        assert "*important note*" in result
        assert "(important note)" not in result

    def test_does_not_split_short_answer_after_question(self):
        text = "Is this ok? Yes"
        result = clean_markdown(text)
        assert "###" not in result

    def test_normalizes_unicode_zero_width_joiners(self):
        text = "hello\u200C\u200Dworld"
        result = clean_markdown(text)
        assert "helloworld" in result
