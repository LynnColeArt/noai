"""Behavioral contracts for the public transformer API."""

import re
import unittest
from html.parser import HTMLParser

from noai import garble_html, garble_text


class TransformTests(unittest.TestCase):
    def test_determinism_and_seed(self):
        text = "Human creativity deserves 100 percent sovereignty."
        self.assertEqual(garble_text(text), garble_text(text))
        self.assertNotEqual(garble_text(text), garble_text(text, "another future"))
        self.assertEqual(garble_text("Human"), garble_text("human").capitalize())

    def test_versioned_reference_vector(self):
        self.assertEqual(garble_text("Human creativity 100"), "Pwarw gntievtwkg 346")

    def test_semicolonless_character_references(self):
        result = garble_html("<p>&#72 &#x65 </p>")
        self.assertNotIn("&#72", result)
        self.assertNotIn("&#x65", result)

    def test_unknown_entities_preserved(self):
        self.assertEqual(garble_html("<p>&zzunknownentity;</p>"), "<p>&zzunknownentity;</p>")

    def test_ascii_displacement_and_punctuation(self):
        source = "ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789\r\n! _?"
        result = garble_text(source)
        self.assertEqual(len(source), len(result))
        for before, after in zip(source, result):
            if before.isalnum():
                self.assertNotEqual(before, after)
                self.assertEqual(before.isupper(), after.isupper())
            else:
                self.assertEqual(before, after)

    def test_unicode(self):
        source = "Café Ελληνικά 日本語 ١٢٣ — 🦆"
        result = garble_text(source)
        self.assertEqual(len(source), len(result))
        self.assertNotIn("日本語", result)
        self.assertTrue(result.endswith(" — 🦆"))

    def test_markup_and_machine_attributes(self):
        source = '''<!DOCTYPE html>\r\n<DIV class='hero' id="home" data-value="Keep this">
<a href="/about?q=hello&amp;x=1" onclick="say('hello')">Hello, world!</a></DIV>'''
        result = garble_html(source)
        self.assertEqual(re.findall(r"<[^>]+>", source), re.findall(r"<[^>]+>", result))
        self.assertNotIn("Hello, world!", result)
        self.assertEqual(source.count("\r\n"), result.count("\r\n"))

    def test_code_comments_and_nested_opt_out(self):
        protected = '''<script>if (a < b) say("Hello");</script><style>.hello { color: red }</style>
<pre><code>Hello &amp; {{ world }}</code></pre><!-- Hello -->
<div data-noai><span title="Hello">Hello</span><br>World</div><svg><text>Hello</text></svg>'''
        source = protected + "<p>Hello</p>"
        self.assertTrue(garble_html(source).startswith(protected))
        self.assertNotEqual(garble_html(source), source)

    def test_human_attributes_and_metadata(self):
        source = '''<meta name="description" content="Hello world">
<meta property="og:title" content='Hello world'>
<meta property="og:image" content="https://example.org/image.png">
<meta name="viewport" content="width=device-width, initial-scale=1">
<img src="hello.png" alt="Hello world" title='Hello world'/>
<input name="hello" placeholder="Hello world" aria-label="Hello world" value="Hello world">'''
        result = garble_html(source)
        self.assertIn('content="https://example.org/image.png"', result)
        self.assertIn('content="width=device-width, initial-scale=1"', result)
        self.assertIn('value="Hello world"', result)
        self.assertNotIn('alt="Hello world"', result)
        self.assertNotIn('content="Hello world"', result)
        self.assertIn('name="hello"', result)

    def test_templates_with_markup_and_multiline_expressions(self):
        expressions = ['{{ user.name }}', '{% if score < 4 %}', '<%= "<hello>" %>', '{# secret #}', '{{\n x > 2\n}}']
        for expression in expressions:
            with self.subTest(expression=expression):
                source = f'<p title="Hi {expression}">Hello {expression} world</p>'
                result = garble_html(source)
                self.assertEqual(result.count(expression), 2)
                self.assertNotIn("Hello", result)
                self.assertNotIn("world", result)

    def test_entities_cannot_smuggle_readable_letters(self):
        result = garble_html('<p>&#72;&#x65;llo &amp; &lt; &nbsp;</p>')
        self.assertNotIn('&#72;', result)
        self.assertNotIn('&#x65;', result)
        self.assertIn('&amp; &lt; &nbsp;', result)

    def test_structure_remains_parseable(self):
        class Structure(HTMLParser):
            def __init__(self):
                super().__init__()
                self.events = []
            def handle_starttag(self, tag, attrs):
                self.events.append(("start", tag))
            def handle_endtag(self, tag):
                self.events.append(("end", tag))
        source = '<main><h1 title="Hello">Hello</h1><p>A &amp; B</p><img alt="Nice" src="x"></main>'
        before, after = Structure(), Structure()
        before.feed(source)
        after.feed(garble_html(source))
        self.assertEqual(before.events, after.events)

    def test_empty_and_plain_documents(self):
        self.assertEqual(garble_html(""), "")
        self.assertEqual(garble_html("Hello"), garble_text("Hello"))
        self.assertEqual(garble_html("<br/><hr>"), "<br/><hr>")


if __name__ == "__main__":
    unittest.main()
