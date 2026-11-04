import ast,pathlib,unittest
class SyntaxTest(unittest.TestCase):
 def test_python(self):ast.parse(pathlib.Path('downloader.py').read_text())
