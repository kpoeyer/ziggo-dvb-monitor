import tempfile, unittest
from app.db import Store

class ChangeTests(unittest.TestCase):
    def service(self, **kw):
        x={"service_id":1,"original_network_id":2,"transport_stream_id":3,"name":"Test TV",
           "channel_number":10,"teletext":[],"subtitles":[],"audio":[],"video":[]}
        x.update(kw); return x
    def test_added_changed_removed_with_grace(self):
        with tempfile.NamedTemporaryFile() as f:
            db=Store(f.name)
            a=db.start_scan(); db.apply_scan(a,[self.service()],2)
            b=db.start_scan(); db.apply_scan(b,[self.service(channel_number=11,teletext=[{"pid":50}])],2)
            c=db.start_scan(); db.apply_scan(c,[],2)
            d=db.start_scan(); db.apply_scan(d,[],2)
            changes=db.dashboard()["changes"]
            self.assertEqual([x["kind"] for x in changes].count("added"),1)
            self.assertEqual([x["kind"] for x in changes].count("removed"),1)
            self.assertEqual([x["kind"] for x in changes].count("changed"),2)

if __name__ == '__main__': unittest.main()
