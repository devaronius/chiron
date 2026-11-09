"""Tests for the archive module's tools: register-import.py and archive-lint.py's privacy patterns.

Installed into a consumer at aiOS/tools/vault/tests/ (beside the tools), so run-tests.sh finds them.
Everything happens in a temp directory; the vault is never touched.
"""
import os, re, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
IMPORT = TOOLS / "register-import.py"
LINT = TOOLS / "archive-lint.py"


def xlsx(path, rows):
    """Write a minimal xlsx with inline strings; rows[0] is the header."""
    def col(i):
        return chr(ord("A") + i)
    sheet = "".join(
        f'<row r="{r + 1}">' + "".join(
            f'<c r="{col(i)}{r + 1}" t="inlineStr"><is><t>{v}</t></is></c>' for i, v in enumerate(row) if v != "")
        + "</row>" for r, row in enumerate(rows))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/data.xml" Type="x"/></Relationships>')
        z.writestr("xl/worksheets/data.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   f'<sheetData>{sheet}</sheetData></worksheet>')


def run(*args, ok=True):
    p = subprocess.run([sys.executable, str(IMPORT), *map(str, args)], capture_output=True, text=True)
    if ok:
        assert p.returncode == 0, p.stdout + p.stderr
    return p


def table_rows(note):
    s = Path(note).read_text()
    block = s[s.index("register:begin"):s.index("register:end")]
    lines = [l for l in block.splitlines() if l.startswith("|")]
    cols = [c.strip() for c in lines[0].split("|")[2:-1]]
    return cols, [dict(zip(cols, [c.strip() for c in l.split("|")[2:-1]])) for l in lines[2:]]


class RegisterImport(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.note = self.d / "collectie.md"
        self.note.write_text("# Collectie\n\n## Transcription\n\n")

    def test_init_records_key_and_diff_is_clean(self):
        xlsx(self.d / "r.xlsx", [["jaar", "tot", "naam", "tekst"], ["1883", "1884", "Wetzer", "A"]])
        run("init", self.d / "r.xlsx", self.note, "--key", "jaar,naam")
        self.assertIn("<!-- register:begin key=jaar,naam -->", self.note.read_text())
        self.assertIn("0 difference(s)", run("diff", self.d / "r.xlsx", self.note).stdout)

    def test_apply_keeps_note_only_and_renamed_columns(self):
        xlsx(self.d / "v1.xlsx", [["jaar", "naam", "tekst"], ["1883", "Wetzer", "A"], ["1890", "Bree", "B"]])
        run("init", self.d / "v1.xlsx", self.note)
        s = self.note.read_text().replace("| jaar | naam | tekst |", "| jaar | naam | tekst | opmerking |")
        s = s.replace("|---|---|---|---|", "|---|---|---|---|---|").replace("| A |", "| A | eigen noot |").replace("| B |", "| B | tweede |")
        self.note.write_text(s)
        # v2 renames "tekst" to "opschrift" and changes row 1 only
        xlsx(self.d / "v2.xlsx", [["jaar", "naam", "opschrift"], ["1883", "Wetzer", "A2"], ["1890", "Bree", "B"]])
        run("apply", self.d / "v2.xlsx", self.note, "--rows", "1")
        cols, rows = table_rows(self.note)
        self.assertEqual(cols, ["jaar", "naam", "tekst", "opmerking", "opschrift"])
        self.assertEqual(rows[0]["opmerking"], "eigen noot")      # note-only column kept
        self.assertEqual(rows[0]["tekst"], "A")                   # old column kept
        self.assertEqual(rows[0]["opschrift"], "A2")
        self.assertEqual(rows[1]["tekst"], "B")                   # unapplied row untouched
        self.assertEqual(rows[1]["opmerking"], "tweede")

    def test_duplicate_keys_apply_updates_the_row_diff_paired(self):
        xlsx(self.d / "v1.xlsx", [["jaar", "naam", "tekst"], ["1965", "Lierop", "eerste"], ["1965", "Lierop", "tweede"]])
        run("init", self.d / "v1.xlsx", self.note)
        xlsx(self.d / "v2.xlsx", [["jaar", "naam", "tekst"], ["1965", "Lierop", "eerste"], ["1965", "Lierop", "tweede NIEUW"]])
        out = run("diff", self.d / "v2.xlsx", self.note).stdout
        self.assertIn("register row   2", out)
        self.assertIn("(note row 2)", out)
        run("apply", self.d / "v2.xlsx", self.note, "--rows", "2")
        _, rows = table_rows(self.note)
        self.assertEqual([r["tekst"] for r in rows], ["eerste", "tweede NIEUW"])

    def test_new_row_is_appended_and_count_is_real(self):
        xlsx(self.d / "v1.xlsx", [["jaar", "naam"], ["1883", "Wetzer"]])
        run("init", self.d / "v1.xlsx", self.note)
        xlsx(self.d / "v2.xlsx", [["jaar", "naam"], ["1883", "Wetzer"], ["1884", "Cuypers"]])
        out = run("apply", self.d / "v2.xlsx", self.note, "--rows", "2,9").stdout
        self.assertIn("skipped register row 9", out)
        self.assertIn("applied 1 row(s)", out)
        self.assertEqual(len(table_rows(self.note)[1]), 2)

    def test_empty_sheet_is_a_clear_error(self):
        xlsx(self.d / "e.xlsx", [])
        p = run("init", self.d / "e.xlsx", self.note, ok=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("empty", p.stderr)
        self.assertNotIn("Traceback", p.stderr)


class PrivacyPatterns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = LINT.read_text()
        ns = {"re": re}
        exec(src[src.index("FORBIDDEN = ["):src.index("COMMENT =")], ns)
        cls.F = ns["FORBIDDEN"]

    def hits(self, text):
        return [w for rx, w, fl in self.F if re.search(rx, text, fl)]

    def test_flags_personal_data(self):
        for t in ["geboren 1923", "Geboortedatum: 1 mei", "Woonadres Markt 1", "Telefoonnummer bekend",
                  "06-12345678", "0492 123456", "was lang ziek", "j@example.org"]:
            self.assertTrue(self.hits(t), t)

    def test_does_not_flag_organisation_facts(self):
        for t in ["12-05-1987", "1987-05-12", "14-03-1923", "1985 - 1990", "overleden 1923",
                  "opening van het ziekenhuis", "koning 1883-84, 1894-95", "jonge deken 2011-2016"]:
            self.assertEqual(self.hits(t), [], t)

    def test_person_template_comment_is_not_scanned(self):
        tpl = (TOOLS.parent.parent / "templates" / "person.template.md")
        if not tpl.is_file():
            self.skipTest("templates not installed beside the tools")
        text = re.sub(r"<!--.*?-->", "", tpl.read_text(), flags=re.S)
        self.assertEqual(self.hits(text), [])


if __name__ == "__main__":
    unittest.main()
