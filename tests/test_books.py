import unittest
from books import page_url

class BookScopeTest(unittest.TestCase):
    def test_magazines_and_articles_are_excluded(self):
        for link in ('library.aspx?libcatid=2&catid=18', 'library.aspx?libcatid=53&catid=18',
                     'category.aspx?catid=20', 'library.aspx?catid=20&libcatid=99',
                     'LIBRARY.aspx?LibCatID=53&CatID=18'):
            self.assertIsNone(page_url('https://www.stmark-kw.net/' + link))

    def test_remaining_library_sections_are_kept(self):
        for lib in (5, 7, 23, 74, 75, 10106):
            self.assertIsNotNone(page_url(f'https://www.stmark-kw.net/library.aspx?libcatid={lib}&catid=18'))

    def test_external_pages_and_forms_are_not_crawled(self):
        for u in ('https://external.example/library.aspx?libcatid=5',
                  'https://www.stmark-kw.net/AddClassified.aspx?catid=35'):
            self.assertIsNone(page_url(u))

    def test_query_order_deduplicates(self):
        self.assertEqual(page_url('https://www.stmark-kw.net/library.aspx?catid=18&libcatid=5'),
                         page_url('https://www.stmark-kw.net/library.aspx?libcatid=5&catid=18'))
