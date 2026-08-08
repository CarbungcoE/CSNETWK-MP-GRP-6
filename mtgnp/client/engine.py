class ClientEngine:
    def __init__(self, pid):
        self.pid = pid
        self.seq_num = 0
        self.phase = "LOBBY"
        self.active_player = None
        self.priority_holder = None
        
        self.life_totals = {}
        self.hand = []
        self.hand_counts = {}
        self.library_counts = {}
        self.battlefield = {}
        self.graveyard = {}
        self.stack = []
        self.land_played = False
        self.time_limit = 60000

    def update_state(self, pdu):
        if "seq_num" in pdu:
            self.seq_num = pdu["seq_num"]

        state_data = pdu.get("state", {})
        self.phase = state_data.get("phase", self.phase)
        self.active_player = state_data.get("active_player", self.active_player)
        self.priority_holder = state_data.get("priority_holder", self.priority_holder)
        
        if "life_totals" in state_data:
            self.life_totals = state_data["life_totals"]
        if "hand" in state_data:
            self.hand = state_data["hand"]
        if "hand_counts" in state_data:
            self.hand_counts = state_data["hand_counts"]
        if "library_counts" in state_data:
            self.library_counts = state_data["library_counts"]
        if "battlefield" in state_data:
            self.battlefield = state_data["battlefield"]
        if "graveyard" in state_data:
            self.graveyard = state_data["graveyard"]
        if "stack" in state_data:
            self.stack = state_data["stack"]
        if "land_played_this_turn" in state_data:
            self.land_played = state_data["land_played_this_turn"]

    def set_priority(self, pdu):
        self.seq_num = pdu.get("seq_num", self.seq_num)
        self.priority_holder = pdu.get("player_id", self.pid)
        self.time_limit = pdu.get("time_limit_ms", 60000)

    def draw_board(self):
        print("\n" + "="*55)
        print(f" PHASE: {self.phase} | ACTIVE: {self.active_player} | TURN PLAYER: {self.pid}")
        if self.priority_holder:
            print(f" PRIORITY HOLDER: {self.priority_holder} (Seq #{self.seq_num})")
        print("="*55)

        print("\n--- LIFE TOTALS & HAND COUNTS ---")
        for p, hp in self.life_totals.items():
            hcnt = self.hand_counts.get(p, len(self.hand) if p == self.pid else 0)
            lcnt = self.library_counts.get(p, "?")
            print(f" {p}: {hp} HP | Hand: {hcnt} cards | Deck: {lcnt} left")

        print("\n--- BATTLEFIELD ---")
        for p, perms in self.battlefield.items():
            print(f" [{p}]'s board:")
            if not perms:
                print("   (Empty)")
            for card in perms:
                status = "Tapped" if card.get("tapped") else "Ready"
                if "power" in card:
                    dmg = card.get("damage", 0)
                    sick = " [Sick]" if card.get("summoning_sick") else ""
                    print(f"   > {card.get('id')} ({card.get('power')}/{card.get('toughness')}) - {status}, Dmg: {dmg}{sick}")
                else:
                    print(f"   > {card.get('id')} - {status}")

        if self.stack:
            print("\n--- STACK (Top Resolves First) ---")
            for item in reversed(self.stack):
                print(f"   * [{item.get('stack_item_id')}] {item.get('item_type')} from {item.get('source')} -> Targets: {item.get('targets')}")

        print("\n--- YOUR HAND ---")
        if not self.hand:
            print("   (Empty)")
        else:
            for idx, c in enumerate(self.hand):
                print(f"   [{idx}] {c}")
        print("="*55)
