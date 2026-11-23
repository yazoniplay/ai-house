import unittest
from free_search import parse_results
class FreeSearchTests(unittest.TestCase):
 def test_parses_title_and_snippet(self):
  html='<div class="result"><a class="result__a" href="https://example.com/a">Market <b>Report</b></a><a class="result__snippet">Demand is growing for workflow tools.</a></div>'
  result=parse_results(html);self.assertEqual(len(result),1);self.assertEqual(result[0]["title"],"Market Report");self.assertEqual(result[0]["url"],"https://example.com/a");self.assertIn("Demand is growing",result[0]["content"])
 def test_redirect_decode_and_dedupe(self):
  html='<a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpost">Post</a><a class="result__a" href="https://example.com/post">Duplicate</a>'
  self.assertEqual([x["url"] for x in parse_results(html)],["https://example.com/post"])
if __name__=="__main__":unittest.main()
