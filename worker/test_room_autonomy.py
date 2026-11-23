import unittest
from room_autonomy import default_room_plan,normalize_room_plan
class RoomAutonomyTests(unittest.TestCase):
 def test_plan_derives_product_and_room_briefs_from_business(self):
  b={"name":"Inbox Helper","customer":"independent shops","problem":"repetitive order admin","solution":"a simple order workflow"};p=default_room_plan(b,3)
  self.assertIn("Inbox Helper",p["coding_product"]["title"]);self.assertIn("independent shops",p["coding_product"]["target_user"]);self.assertIn("cycle 3",p["youtube"]["brief"]);self.assertIn("AI-selected",p["computer"]["mission"])
 def test_missing_fields_fall_back_and_computer_mission_is_safe(self):
  p=normalize_room_plan({"name":"Test"},{"coding_product":{"title":"AI chosen app"},"computer":{"mission":"Open editor"}},2)
  self.assertEqual(p["coding_product"]["title"],"AI chosen app");self.assertTrue(p["coding_product"]["brief"]);self.assertIn("Never publish",p["computer"]["mission"]);self.assertLessEqual(len(p["computer"]["mission"]),4000)
if __name__=="__main__":unittest.main()
