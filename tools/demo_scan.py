#!/usr/bin/env python3
import json
print(json.dumps([
 {"service_id":10001,"original_network_id":5555,"transport_stream_id":31,"name":"NPO 1","provider":"Ziggo","channel_number":1,"frequency":474000000,"modulation":"QAM/256","symbol_rate":6900000,"encrypted":False,"teletext":[{"pid":36,"language":"nld"}],"subtitles":[{"pid":51,"language":"nld"}],"video":[{"pid":101}],"audio":[{"pid":102,"language":"nld"}]},
 {"service_id":10002,"original_network_id":5555,"transport_stream_id":31,"name":"NPO 2","provider":"Ziggo","channel_number":2,"frequency":474000000,"modulation":"QAM/256","symbol_rate":6900000,"encrypted":False,"teletext":[{"pid":46,"language":"nld"}],"subtitles":[],"video":[{"pid":201}],"audio":[{"pid":202,"language":"nld"}]},
 {"service_id":20004,"original_network_id":5555,"transport_stream_id":42,"name":"RTL 4","provider":"Ziggo","channel_number":4,"frequency":490000000,"modulation":"QAM/256","symbol_rate":6900000,"encrypted":True,"teletext":[{"pid":66,"language":"nld"}],"subtitles":[],"video":[{"pid":401}],"audio":[{"pid":402,"language":"nld"}]}
], ensure_ascii=False))
