import socket, select
from mtgnp.common.framing import send_pdu, recv_pdu
HOST='127.0.0.1'; PORT=4444
DECK=['lightning_bolt_001','lightning_bolt_002','lightning_bolt_003','shock_001','shock_002','goblin_guide_001','mountain_001','mountain_002']
p1=socket.socket(); p2=socket.socket(); p1.connect((HOST,PORT)); p2.connect((HOST,PORT)); socks={p1:'player_1',p2:'player_2'}
def recv(timeout=5):
 r,_,_=select.select([p1,p2],[],[],timeout)
 if not r: raise RuntimeError('timeout')
 s=r[0]; return s,socks[s],recv_pdu(s)
def ready(s,p,session): send_pdu(s,{'type':'PLAYER_READY','seq_num':1,'session_id':session,'player_id':p,'deck_list':DECK})
ready(p1,'player_1','restart'); recv(); ready(p2,'player_2','restart')
seen={}
while len(seen)<2:
 s,p,m=recv();
 if m and m.get('type')=='GAME_STATE_UPDATE' and m.get('state',{}).get('phase')=='MULLIGAN': seen[p]=m
send_pdu(p1,{'type':'MULLIGAN_CHOICE','seq_num':seen['player_1']['seq_num'],'session_id':'restart','player_id':'player_1','keep':True,'cards_to_bottom':[]})
# Player 1's keep refreshes player 2's mulligan token.
while True:
 s,p,m=recv()
 if p == 'player_2' and m and m.get('type') == 'GAME_STATE_UPDATE' and m.get('state',{}).get('phase') == 'MULLIGAN':
  seen['player_2']=m
  break
send_pdu(p2,{'type':'MULLIGAN_CHOICE','seq_num':seen['player_2']['seq_num'],'session_id':'restart','player_id':'player_2','keep':True,'cards_to_bottom':[]})
# consume mulligan and initial turn state
for _ in range(8):
 s,p,m=recv()
 if m and m.get('type')=='GAME_STATE_UPDATE' and m.get('state',{}).get('phase')=='UPKEEP': break
# concede from player 1 using latest received server sequence (the server accepts the exempt action)
send_pdu(p1,{'type':'CONCEDE','seq_num':m.get('seq_num',1),'session_id':'restart','player_id':'player_1'})
seen_go=False
while not seen_go:
 s,p,m=recv()
 if m and m.get('type')=='GAME_OVER':
  assert m['reason']=='CONCEDE'; assert m['winner_id']=='player_2'; seen_go=True
# same TCP connections, fresh ready
ready(p1,'player_1','restart'); ready(p2,'player_2','restart')
seen={}
while len(seen)<2:
 s,p,m=recv()
 if m and m.get('type')=='GAME_STATE_UPDATE' and m.get('state',{}).get('phase')=='MULLIGAN': seen[p]=m
assert len(seen)==2
print('SESSION RESTART milestone passed')
p1.close(); p2.close()
