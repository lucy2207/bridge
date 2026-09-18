"""
Bridge Cheater - main entry point
Bridge bidding assistant (Five Card Major system)
"""
import math
import customtkinter as ctk
import bidding_engine as engine
import play_engine as play
import game_log

# ----- "Card table felt" palette (sampled from reference image) -----
FELT_GREEN = "#237a3f"       # brighter oval table surface
FELT_GREEN_DARK = "#1c5c30"  # base background
TEXTURE_LINE = "#17492a"     # diamond quilt line color
GOLD = "#d4af37"
GOLD_BRIGHT = "#ffd76b"
CREAM = "#f5f0e6"
CREAM_HOVER = "#e3d6ab"
GOLD_HOVER = "#a67f1f"
CARD_BACK = "#7a1f2b"
RED_SUIT = "#c0392b"
BLACK_SUIT = "#1a1a1a"
PANEL_BG = "#164227"
SEAT_FONT = ("Georgia", 13, "bold")

ctk.set_appearance_mode("dark")

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["spades", "hearts", "diamonds", "clubs"]
SUIT_ORDER = {"spades": 0, "hearts": 1, "diamonds": 2, "clubs": 3}
SUIT_SYMBOL = {"spades": "♠", "hearts": "♥", "diamonds": "♦", "clubs": "♣"}
SYMBOL_TO_SUITKEY = {v: k for k, v in SUIT_SYMBOL.items()}
SUIT_COLOR = {"spades": BLACK_SUIT, "hearts": RED_SUIT, "diamonds": RED_SUIT, "clubs": BLACK_SUIT}
RANK_ORDER = {r: i for i, r in enumerate(RANKS)}

SEATS = ["north", "east", "south", "west"]
PARTNER_SEAT = "north"   # you are always South, partner is always North
STRAINS = ["♣", "♦", "♥", "♠", "NT"]


def next_seat(seat):
    return SEATS[(SEATS.index(seat) + 1) % 4]


def is_opponent(seat_a, seat_b):
    ns = {"north", "south"}
    return (seat_a in ns) != (seat_b in ns)


# ============================================================
#  DRAWING HELPERS
# ============================================================
def draw_diamond_texture(canvas, w, h, spacing=46):
    canvas.delete("texture")
    if w <= 1 or h <= 1:
        return
    for offset in range(-h, w, spacing):
        canvas.create_line(offset, 0, offset + h, h, fill=TEXTURE_LINE, width=1, tags="texture")
        canvas.create_line(offset, h, offset + h, 0, fill=TEXTURE_LINE, width=1, tags="texture")
    canvas.tag_lower("texture")


def rounded_rect(canvas, x1, y1, x2, y2, radius=10, **kwargs):
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def draw_card_face(canvas, x, y, rank, suit, w=58, h=82, bg=CREAM, outline="#c9bd9a", outline_w=1.5, tags=()):
    color = SUIT_COLOR[suit]
    symbol = SUIT_SYMBOL[suit]
    rounded_rect(canvas, x, y, x + w, y + h, radius=8, fill=bg, outline=outline, width=outline_w, tags=tags)
    corner_font_size = max(9, int(w * 0.19))
    center_font_size = max(16, int(w * 0.40))
    canvas.create_text(x + w * 0.17, y + h * 0.15, text=rank, fill=color,
                        font=("Georgia", corner_font_size, "bold"), tags=tags)
    canvas.create_text(x + w * 0.17, y + h * 0.32, text=symbol, fill=color,
                        font=("Georgia", corner_font_size, "bold"), tags=tags)
    canvas.create_text(x + w / 2, y + h / 2, text=symbol, fill=color,
                        font=("Georgia", center_font_size, "bold"), tags=tags)
    canvas.create_text(x + w * 0.83, y + h * 0.85, text=rank, fill=color,
                        font=("Georgia", corner_font_size, "bold"), angle=180, tags=tags)
    canvas.create_text(x + w * 0.83, y + h * 0.68, text=symbol, fill=color,
                        font=("Georgia", corner_font_size, "bold"), angle=180, tags=tags)


def _rotate(dx, dy, angle_deg):
    ang = math.radians(angle_deg)
    return (dx * math.cos(ang) - dy * math.sin(ang),
            dx * math.sin(ang) + dy * math.cos(ang))


def draw_card_back(canvas, cx, cy, angle_deg, w=34, h=48, highlight=False, tags=()):
    hw, hh = w / 2, h / 2
    pts = []
    for dx, dy in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]:
        rx, ry = _rotate(dx, dy, angle_deg)
        pts.extend([cx + rx, cy + ry])
    outline_color = GOLD_BRIGHT if highlight else GOLD
    outline_w = 2.2 if highlight else 1.1
    canvas.create_polygon(pts, fill=CARD_BACK, outline=outline_color,
                           width=outline_w, tags=tags)
    inner = []
    for dx, dy in [(-hw * 0.4, 0), (0, -hh * 0.35), (hw * 0.4, 0), (0, hh * 0.35)]:
        rx, ry = _rotate(dx, dy, angle_deg)
        inner.extend([cx + rx, cy + ry])
    canvas.create_polygon(inner, fill="", outline=outline_color, width=1, tags=tags)


def add_felt_background(frame):
    canvas = ctk.CTkCanvas(frame, bg=FELT_GREEN_DARK, highlightthickness=0)
    canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
    canvas.bind("<Configure>", lambda e: draw_diamond_texture(canvas, e.width, e.height))
    return canvas


class BridgeCheaterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Bridge Cheater")
        self.geometry("1100x750")
        self.minsize(900, 650)
        self.configure(fg_color=FELT_GREEN_DARK)

        self.player_hand = []
        self.first_bidder = None
        self.auction = []  # list of (seat, bid_str)

        # play phase
        self.contract = None      # (level, strain, declarer_seat) or None
        self.dummy_seat = None
        self.dummy_hand = []      # dummy's 13 cards, once entered
        self.north_hand = []      # partner's hand, only collected when partner is declaring
        self.pending_entry = None  # (kind, seat) waiting to be entered before play starts
        self.tricks_won = {"NS": 0, "EW": 0}
        self.played_cards = {s: [] for s in SEATS}   # cards each seat has played this deal
        self.current_trick = []   # list of (seat, (rank, suit))
        self.trick_leader = None
        self.current_leader = None
        self.game_log = game_log.GameLog()

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for ScreenClass in (WelcomeScreen, HandSelectionScreen, TableScreen, BiddingScreen,
                             DummyEntryScreen, PlayScreen):
            frame = ScreenClass(parent=self.container, controller=self)
            self.frames[ScreenClass.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("WelcomeScreen")

    def show_frame(self, name):
        frame = self.frames[name]
        if hasattr(frame, "on_show"):
            frame.on_show()
        frame.tkraise()


# ============================================================
#  SCREEN 1 - WELCOME
# ============================================================
class WelcomeScreen(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=FELT_GREEN_DARK)
        self.controller = controller
        add_felt_background(self)

        title = ctk.CTkLabel(
            self, text="Welcome to my Bridge Cheater",
            font=ctk.CTkFont(family="Georgia", size=34, weight="bold"), text_color=GOLD,
        )
        title.place(relx=0.5, rely=0.28, anchor="center")

        subtitle = ctk.CTkLabel(
            self, text="Five Card Major",
            font=ctk.CTkFont(family="Georgia", size=16, slant="italic"), text_color=CREAM,
        )
        subtitle.place(relx=0.5, rely=0.36, anchor="center")

        start_btn = ctk.CTkButton(
            self, text="New Game", font=ctk.CTkFont(size=18, weight="bold"),
            fg_color=CARD_BACK, hover_color="#5c1620", text_color=CREAM,
            corner_radius=12, width=240, height=56,
            command=lambda: controller.show_frame("HandSelectionScreen"),
        )
        start_btn.place(relx=0.5, rely=0.52, anchor="center")

        exit_btn = ctk.CTkButton(
            self, text="Exit", font=ctk.CTkFont(size=14),
            fg_color="transparent", border_width=2, border_color=CREAM,
            hover_color=FELT_GREEN, text_color=CREAM, corner_radius=12,
            width=240, height=42, command=controller.destroy,
        )
        exit_btn.place(relx=0.5, rely=0.62, anchor="center")


# ============================================================
#  SCREEN 2 - HAND SELECTION (13 cards, drawn as real card tiles)
# ============================================================
class HandSelectionScreen(ctk.CTkFrame):
    CARD_W, CARD_H = 50, 70

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=FELT_GREEN_DARK)
        self.controller = controller
        self.selected = set()
        self.tiles = {}

        add_felt_background(self)

        header = ctk.CTkLabel(
            self, text="Choose your 13 cards",
            font=ctk.CTkFont(family="Georgia", size=26, weight="bold"), text_color=GOLD,
        )
        header.pack(pady=(24, 4))

        self.counter_label = ctk.CTkLabel(
            self, text="0 / 13 selected", font=ctk.CTkFont(size=15), text_color=CREAM,
        )
        self.counter_label.pack(pady=(0, 16))

        grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        grid_frame.pack(pady=4)

        for row, suit in enumerate(SUITS):
            for col, rank in enumerate(RANKS):
                key = (rank, suit)
                tile = ctk.CTkCanvas(
                    grid_frame, width=self.CARD_W, height=self.CARD_H,
                    bg=FELT_GREEN_DARK, highlightthickness=0,
                )
                tile.grid(row=row, column=col, padx=3, pady=4)
                tile.bind("<Button-1>", lambda e, k=key: self.toggle_card(k))
                tile.bind("<Enter>", lambda e, k=key: self._render(k, hover=True))
                tile.bind("<Leave>", lambda e, k=key: self._render(k, hover=False))
                self.tiles[key] = tile
                self._render(key, hover=False)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=20)

        self.confirm_btn = ctk.CTkButton(
            btn_row, text="Confirm my hand", state="disabled",
            fg_color=CARD_BACK, hover_color="#5c1620", text_color=CREAM,
            corner_radius=12, width=200, height=48,
            font=ctk.CTkFont(size=16, weight="bold"), command=self.confirm_hand,
        )
        self.confirm_btn.grid(row=0, column=0, padx=10)

        back_btn = ctk.CTkButton(
            btn_row, text="Back", fg_color="transparent",
            border_width=2, border_color=CREAM, text_color=CREAM,
            hover_color=FELT_GREEN, corner_radius=12, width=140, height=48,
            command=lambda: controller.show_frame("WelcomeScreen"),
        )
        back_btn.grid(row=0, column=1, padx=10)

    def _render(self, key, hover):
        rank, suit = key
        tile = self.tiles[key]
        tile.delete("all")
        is_selected = key in self.selected
        if is_selected:
            bg = GOLD_HOVER if hover else GOLD
        else:
            bg = CREAM_HOVER if hover else CREAM
        draw_card_face(tile, 0, 0, rank, suit, w=self.CARD_W, h=self.CARD_H,
                        bg=bg, outline="#c9bd9a", outline_w=1.2)

    def toggle_card(self, key):
        if key in self.selected:
            self.selected.remove(key)
        else:
            if len(self.selected) >= 13:
                return
            self.selected.add(key)
        self._render(key, hover=True)

        self.counter_label.configure(text=f"{len(self.selected)} / 13 selected")
        self.confirm_btn.configure(state="normal" if len(self.selected) == 13 else "disabled")

    def confirm_hand(self):
        self.controller.player_hand = list(self.selected)
        self.controller.show_frame("TableScreen")

    def on_show(self):
        self.selected.clear()
        for key in self.tiles:
            self._render(key, hover=False)
        self.counter_label.configure(text="0 / 13 selected")
        self.confirm_btn.configure(state="disabled")


# ============================================================
#  SCREEN 3 - GAME TABLE
# ============================================================
class TableScreen(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=FELT_GREEN_DARK)
        self.controller = controller
        self.hit_boxes = {}
        self.selected_seat = None

        self.canvas = ctk.CTkCanvas(self, bg=FELT_GREEN_DARK, highlightthickness=0)
        self.canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<Button-1>", self._on_click)

        self.status_label = ctk.CTkLabel(
            self, text="Who bids first? Click on a player.",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=GOLD,
        )
        self.status_label.place(relx=0.5, rely=0.05, anchor="center")

        back_btn = ctk.CTkButton(
            self, text="Back", fg_color="transparent",
            border_width=2, border_color=CREAM, text_color=CREAM,
            hover_color=FELT_GREEN, corner_radius=12, width=110, height=36,
            command=lambda: controller.show_frame("WelcomeScreen"),
        )
        back_btn.place(relx=0.03, rely=0.04, anchor="nw")

        self.start_bidding_btn = ctk.CTkButton(
            self, text="Start bidding →", state="disabled",
            fg_color=CARD_BACK, hover_color="#5c1620", text_color=CREAM,
            corner_radius=12, width=200, height=46,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=lambda: controller.show_frame("BiddingScreen"),
        )
        self.start_bidding_btn.place(relx=0.97, rely=0.04, anchor="ne")

    def _on_click(self, event):
        for seat, (x1, y1, x2, y2) in self.hit_boxes.items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.select_first_bidder(seat)
                return

    def select_first_bidder(self, seat):
        self.controller.first_bidder = seat
        self.selected_seat = seat
        self.controller.game_log.set_first_bidder(seat)
        self.status_label.configure(
            text=f"{seat.capitalize()} bids first."
        )
        self.start_bidding_btn.configure(state="normal")
        self._redraw()

    def _draw_fan(self, cx, cy, seat, orientation):
        n = 13
        highlight = self.selected_seat == seat
        pts = []
        for i in range(n):
            t = (i - (n - 1) / 2) / ((n - 1) / 2)
            if orientation == "horizontal":
                angle = t * 24
                x = cx + t * 105
                y = cy + abs(t) * 11
            else:
                base = 90 if seat == "west" else -90
                angle = base + t * 24
                y = cy + t * 92
                x = cx + (abs(t) * 10 if seat == "west" else -abs(t) * 10)
            draw_card_back(self.canvas, x, y, angle, highlight=highlight,
                            tags=(f"seat_{seat}",))
            pts.append((x, y))

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        pad = 26
        self.hit_boxes[seat] = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

        label_color = GOLD_BRIGHT if highlight else CREAM
        if orientation == "horizontal":
            self.canvas.create_text(cx, cy - 42, text=seat.capitalize(),
                                     fill=label_color, font=SEAT_FONT)
        else:
            label_x = cx - 44 if seat == "west" else cx + 44
            self.canvas.create_text(label_x, cy, text=seat.capitalize(),
                                     fill=label_color, font=SEAT_FONT)

    def _redraw(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            return

        draw_diamond_texture(self.canvas, w, h)

        margin_x, margin_y = w * 0.10, h * 0.30
        self.canvas.create_oval(
            margin_x, margin_y, w - margin_x, h - margin_y,
            fill=FELT_GREEN, outline=GOLD, width=3,
        )

        self._draw_fan(w * 0.5, h * 0.20, "north", "horizontal")
        self._draw_fan(w * 0.14, h * 0.5, "west", "vertical")
        self._draw_fan(w * 0.86, h * 0.5, "east", "vertical")

        card_w, card_h = 50, 70
        hand = sorted(
            self.controller.player_hand,
            key=lambda c: (SUIT_ORDER[c[1]], -RANK_ORDER[c[0]]),
        )
        total_w = len(hand) * (card_w - 12) + 12 if hand else 0
        start_x = w / 2 - total_w / 2
        label_y = h * 0.80
        cards_y = label_y + 16

        highlight = self.selected_seat == "south"
        label_color = GOLD_BRIGHT if highlight else CREAM
        self.canvas.create_text(w * 0.5, label_y, text="You (South)",
                                 fill=label_color, font=SEAT_FONT)

        if highlight:
            rounded_rect(
                self.canvas, start_x - 10, cards_y - 8,
                start_x + total_w + 10, cards_y + card_h + 8,
                radius=12, fill="", outline=GOLD_BRIGHT, width=2.5,
            )

        for i, (rank, suit) in enumerate(hand):
            draw_card_face(self.canvas, start_x + i * (card_w - 12), cards_y, rank, suit,
                            w=card_w, h=card_h)

        self.hit_boxes["south"] = (
            start_x - 12, label_y - 14, start_x + max(total_w, 60) + 12, cards_y + card_h + 10,
        )

    def on_show(self):
        if self.controller.game_log.has_content():
            self.controller.game_log.finalize("abandoned")
        self.controller.game_log = game_log.GameLog()
        self.controller.game_log.set_hand("south", self.controller.player_hand)

        self.controller.first_bidder = None
        self.controller.auction = []
        self.controller.contract = None
        self.controller.dummy_seat = None
        self.controller.dummy_hand = []
        self.controller.north_hand = []
        self.controller.pending_entry = None
        self.selected_seat = None
        self.start_bidding_btn.configure(state="disabled")
        self.status_label.configure(text="Who bids first? Click on a player.")
        self._redraw()


# ============================================================
#  SCREEN 4 - BIDDING
# ============================================================
class BiddingScreen(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=FELT_GREEN_DARK)
        self.controller = controller
        self.current_suggestion_bid = None
        add_felt_background(self)

        # ---- header / status ----
        self.status_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=17, weight="bold"), text_color=GOLD,
        )
        self.status_label.pack(pady=(16, 4))

        hand_panel = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=12)
        hand_panel.pack(pady=(0, 10), padx=16, fill="x")
        ctk.CTkLabel(
            hand_panel, text="Your hand", font=ctk.CTkFont(size=14, weight="bold"),
            text_color=GOLD,
        ).pack(pady=(10, 2))
        self.hand_breakdown_label = ctk.CTkLabel(
            hand_panel, text="", font=ctk.CTkFont(size=13), text_color=CREAM,
        )
        self.hand_breakdown_label.pack(pady=(0, 4))
        self.suggestion_label = ctk.CTkLabel(
            hand_panel, text="", font=ctk.CTkFont(size=14, weight="bold"), text_color=GOLD_BRIGHT,
            wraplength=760, justify="center",
        )
        self.suggestion_label.pack(pady=(0, 10))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_columnconfigure(2, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # ---- left: partner info panel ----
        partner_panel = ctk.CTkFrame(body, fg_color=PANEL_BG, corner_radius=12)
        partner_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(
            partner_panel, text="What we know about partner",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=GOLD, wraplength=200,
        ).pack(pady=(12, 6), padx=10)
        partner_scroll = ctk.CTkScrollableFrame(partner_panel, fg_color="transparent", height=200)
        partner_scroll.pack(fill="both", expand=True, padx=6, pady=(0, 10))
        self.partner_info_label = ctk.CTkLabel(
            partner_scroll, text="No bids from partner yet.",
            font=ctk.CTkFont(size=12), text_color=CREAM, wraplength=190, justify="left",
        )
        self.partner_info_label.pack(padx=6, pady=4, anchor="n")

        # ---- middle: auction table ----
        auction_panel = ctk.CTkFrame(body, fg_color=PANEL_BG, corner_radius=12)
        auction_panel.grid(row=0, column=1, sticky="nsew", padx=10)
        header_row = ctk.CTkFrame(auction_panel, fg_color="transparent")
        header_row.pack(pady=(12, 4))
        for seat in ["north", "east", "south", "west"]:
            ctk.CTkLabel(
                header_row, text=seat.capitalize(), width=90,
                font=ctk.CTkFont(size=13, weight="bold"), text_color=GOLD,
            ).pack(side="left", padx=4)
        self.auction_rows_frame = ctk.CTkScrollableFrame(auction_panel, fg_color="transparent", height=200)
        self.auction_rows_frame.pack(pady=4, fill="both", expand=True)

        # ---- right: East & West info panels (both stay on screen the whole auction) ----
        right_col = ctk.CTkFrame(body, fg_color="transparent")
        right_col.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        right_col.grid_rowconfigure(0, weight=1)
        right_col.grid_rowconfigure(1, weight=1)
        right_col.grid_columnconfigure(0, weight=1)

        east_panel = ctk.CTkFrame(right_col, fg_color=PANEL_BG, corner_radius=12)
        east_panel.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        ctk.CTkLabel(
            east_panel, text="East's bidding",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=GOLD, wraplength=200,
        ).pack(pady=(12, 6), padx=10)
        east_scroll = ctk.CTkScrollableFrame(east_panel, fg_color="transparent")
        east_scroll.pack(fill="both", expand=True, padx=6, pady=(0, 10))
        self.east_info_label = ctk.CTkLabel(
            east_scroll, text="No bids yet.", font=ctk.CTkFont(size=12), text_color=CREAM,
            wraplength=190, justify="left",
        )
        self.east_info_label.pack(padx=6, pady=4, anchor="n")

        west_panel = ctk.CTkFrame(right_col, fg_color=PANEL_BG, corner_radius=12)
        west_panel.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        ctk.CTkLabel(
            west_panel, text="West's bidding",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=GOLD, wraplength=200,
        ).pack(pady=(12, 6), padx=10)
        west_scroll = ctk.CTkScrollableFrame(west_panel, fg_color="transparent")
        west_scroll.pack(fill="both", expand=True, padx=6, pady=(0, 10))
        self.west_info_label = ctk.CTkLabel(
            west_scroll, text="No bids yet.", font=ctk.CTkFont(size=12), text_color=CREAM,
            wraplength=190, justify="left",
        )
        self.west_info_label.pack(padx=6, pady=4, anchor="n")


        # ---- bottom: bidding box ----
        box = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=12)

        self.bid_buttons = {}
        grid = ctk.CTkFrame(box, fg_color="transparent")
        grid.pack(padx=12, pady=(12, 6))
        for col, strain in enumerate(STRAINS):
            ctk.CTkLabel(grid, text=strain, width=52,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=RED_SUIT if strain in ("♥", "♦") else CREAM
                         ).grid(row=0, column=col + 1, pady=(0, 2))
        for level in range(1, 8):
            ctk.CTkLabel(grid, text=str(level), width=24,
                         font=ctk.CTkFont(size=12), text_color=CREAM
                         ).grid(row=level, column=0, padx=(0, 4))
            for col, strain in enumerate(STRAINS):
                btn = ctk.CTkButton(
                    grid, text=f"{level}{strain}", width=52, height=30,
                    corner_radius=6, fg_color=CREAM, text_color=BLACK_SUIT,
                    hover_color=GOLD, font=ctk.CTkFont(size=12, weight="bold"),
                    command=lambda lv=level, s=strain: self.make_call(f"{lv}{s}"),
                )
                btn.grid(row=level, column=col + 1, padx=2, pady=2)
                self.bid_buttons[(level, strain)] = btn

        special_row = ctk.CTkFrame(box, fg_color="transparent")
        special_row.pack(pady=(4, 12))
        self.pass_btn = ctk.CTkButton(
            special_row, text="Pass", width=90, height=34, corner_radius=8,
            fg_color="#3d3d3d", hover_color="#565656", text_color=CREAM,
            font=ctk.CTkFont(size=13, weight="bold"), command=lambda: self.make_call("Pass"),
        )
        self.pass_btn.pack(side="left", padx=6)
        self.double_btn = ctk.CTkButton(
            special_row, text="Double (X)", width=110, height=34, corner_radius=8,
            fg_color=CARD_BACK, hover_color="#5c1620", text_color=CREAM,
            font=ctk.CTkFont(size=13, weight="bold"), command=lambda: self.make_call("X"),
        )
        self.double_btn.pack(side="left", padx=6)
        self.redouble_btn = ctk.CTkButton(
            special_row, text="Redouble (XX)", width=130, height=34, corner_radius=8,
            fg_color=CARD_BACK, hover_color="#5c1620", text_color=CREAM,
            font=ctk.CTkFont(size=13, weight="bold"), command=lambda: self.make_call("XX"),
        )
        self.redouble_btn.pack(side="left", padx=6)

        nav_row = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkButton(
            nav_row, text="Back to table", fg_color="transparent",
            border_width=2, border_color=CREAM, text_color=CREAM,
            hover_color=FELT_GREEN, corner_radius=10, width=140, height=34,
            command=lambda: controller.show_frame("TableScreen"),
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            nav_row, text="New game", fg_color="transparent",
            border_width=2, border_color=CREAM, text_color=CREAM,
            hover_color=FELT_GREEN, corner_radius=10, width=140, height=34,
            command=lambda: controller.show_frame("WelcomeScreen"),
        ).pack(side="left", padx=6)
        self.play_btn = ctk.CTkButton(
            nav_row, text="Go to play →", state="disabled",
            fg_color=CARD_BACK, hover_color="#5c1620", text_color=CREAM,
            corner_radius=10, width=150, height=34,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._go_to_play,
        )
        self.play_btn.pack(side="left", padx=6)

        # Pack bottom-up so the bidding box and nav buttons always stay put
        # and visible, no matter how tall the auction log or info panels get:
        # nav_row claims the very bottom edge first, box claims the space
        # just above it, and body (the scrollable panels) only gets whatever
        # is left in the middle - it can never push the controls off-screen.
        nav_row.pack(pady=(0, 10), side="bottom")
        box.pack(pady=14, padx=16, side="bottom")
        body.pack(fill="both", expand=True, padx=16, pady=4, side="top")

    def _go_to_play(self):
        try:
            contract = play.parse_contract(self.controller.auction)
            if contract is None:
                self.status_label.configure(text="No contract to play (hand was passed out).")
                return
            level, strain, declarer = contract
            self.controller.contract = contract
            self.controller.dummy_seat = play.dummy_of(declarer)
            self.controller.north_hand = []
            self.controller.pending_entry = None
            self.controller.game_log.set_contract(level, strain, declarer, self.controller.dummy_seat)

            if self.controller.dummy_seat == "south":
                self.controller.dummy_hand = list(self.controller.player_hand)
                if declarer == "north":
                    # Partner is declaring - we don't actually know their hand,
                    # so ask for it too and let the user play/get tips for both.
                    self.controller.pending_entry = ("declarer", "north")
            else:
                self.controller.pending_entry = ("dummy", self.controller.dummy_seat)

            if self.controller.pending_entry:
                self.controller.show_frame("DummyEntryScreen")
            else:
                self.controller.show_frame("PlayScreen")
        except Exception as exc:
            self.status_label.configure(text=f"Couldn't start play: {exc}")

    # ---------------- logic ----------------
    def current_seat(self):
        first = self.controller.first_bidder
        if first is None:
            return None
        return SEATS[(SEATS.index(first) + len(self.controller.auction)) % 4]

    def last_actual_bid(self):
        for seat, bid in reversed(self.controller.auction):
            if bid not in ("Pass", "X", "XX"):
                return seat, bid
        return None, None

    def auction_over(self):
        auction = self.controller.auction
        if len(auction) < 4:
            return False
        last_three = auction[-3:]
        if all(b == "Pass" for _, b in last_three):
            if len(auction) == 4 and all(b == "Pass" for _, b in auction):
                return True
            if any(b != "Pass" for _, b in auction[:-3]):
                return True
        return False

    def make_call(self, bid):
        seat = self.current_seat()
        if seat is None or self.auction_over():
            return
        suggested = self.current_suggestion_bid if seat == "south" else None
        self.controller.game_log.log_bid(seat, bid, suggested)
        self.controller.auction.append((seat, bid))
        self.refresh()

    def _seat_summary(self, seat, auction):
        """Builds the running, persistent read-out of everything a given seat
        has shown through their bidding so far - stays on screen for the
        whole auction instead of only showing the most recent call."""
        calls = [(s, b) for s, b in auction if s == seat]
        if not calls:
            return "No bids yet."
        lines = []
        for i, (s, b) in enumerate(calls):
            idx_in_auction = [j for j, (ss, _) in enumerate(auction) if ss == s][i]
            explanation = engine.explain_call(s, b, auction[:idx_in_auction])
            lines.append(f"• {b}: {explanation}")
        return "\n".join(lines)

    def refresh(self):
        auction = self.controller.auction
        for widget in self.auction_rows_frame.winfo_children():
            widget.destroy()

        # rebuild the auction grid, 4 seats per row starting from first_bidder
        first = self.controller.first_bidder
        seat_slot = {s: SEATS.index(s) for s in SEATS}
        row_cells = None
        for idx, (seat, bid) in enumerate(auction):
            if idx % 4 == 0:
                row_cells = ctk.CTkFrame(self.auction_rows_frame, fg_color="transparent")
                row_cells.pack()
                for _ in range(4):
                    ctk.CTkLabel(row_cells, text="", width=90).pack(side="left", padx=4)
            slot = seat_slot[seat]
            lbl = row_cells.winfo_children()[slot]
            color = GOLD_BRIGHT if seat == "south" else CREAM
            lbl.configure(text=bid, text_color=color, font=ctk.CTkFont(size=13, weight="bold"))

        # persistent per-player info panels - each stays visible for the
        # whole auction, not just while that seat's most recent call is current
        self.partner_info_label.configure(text=self._seat_summary(PARTNER_SEAT, auction))
        self.east_info_label.configure(text=self._seat_summary("east", auction))
        self.west_info_label.configure(text=self._seat_summary("west", auction))

        # your own hand breakdown - always visible, updates live
        stats = engine.hand_stats(self.controller.player_hand)
        self.hand_breakdown_label.configure(text=engine.format_hand_breakdown(stats))

        over = self.auction_over()
        seat = self.current_seat()

        if over:
            seat_final, final_bid = self.last_actual_bid()
            if final_bid is None:
                self.status_label.configure(text="Passed out - no contract.")
                self.play_btn.configure(state="disabled")
                self.controller.game_log.set_result({"NS": 0, "EW": 0}, "passed out")
                self.controller.game_log.finalize("passed out")
            else:
                self.status_label.configure(
                    text=f"Auction over. Final contract: {final_bid} by {seat_final.capitalize()}."
                )
                self.play_btn.configure(state="normal")
            self.suggestion_label.configure(text="")
            self._set_bidding_box_enabled(False)
            return

        self.status_label.configure(text=f"{seat.capitalize()}'s turn to call.")

        if seat == "south":
            bid, why = engine.suggest_bid(
                self.controller.player_hand, auction, "south", PARTNER_SEAT
            )
            self.current_suggestion_bid = bid
            self.suggestion_label.configure(text=f"Suggested: {bid}  —  {why}")
        else:
            self.current_suggestion_bid = None
            self.suggestion_label.configure(
                text=f"Enter what {seat.capitalize()} actually called."
            )

        self._set_bidding_box_enabled(True)

    def _set_bidding_box_enabled(self, enabled):
        last_seat, last_bid = self.last_actual_bid()
        seat = self.current_seat()

        for (level, strain), btn in self.bid_buttons.items():
            legal = enabled
            if enabled and last_bid is not None:
                last_level = int(last_bid[0])
                last_strain = last_bid[1:]
                if level < last_level:
                    legal = False
                elif level == last_level and engine.STRAIN_RANK[strain] <= engine.STRAIN_RANK[last_strain]:
                    legal = False
            btn.configure(state="normal" if legal else "disabled")

        self.pass_btn.configure(state="normal" if enabled else "disabled")

        can_double = enabled and last_bid is not None and seat is not None and \
            is_opponent(seat, last_seat) and (
                len(self.controller.auction) == 0 or self.controller.auction[-1][1] != "X"
            )
        # only allow double right after an opposing bid (not after a pass burying it)
        can_double = can_double and self.controller.auction and self.controller.auction[-1][1] == last_bid
        self.double_btn.configure(state="normal" if can_double else "disabled")

        can_redouble = enabled and self.controller.auction and \
            self.controller.auction[-1][1] == "X" and seat is not None and \
            is_opponent(seat, self.controller.auction[-1][0]) is False and \
            not is_opponent(seat, last_seat)
        can_redouble = enabled and bool(self.controller.auction) and \
            self.controller.auction[-1][1] == "X"
        self.redouble_btn.configure(state="normal" if can_redouble else "disabled")

    def on_show(self):
        for widget in self.auction_rows_frame.winfo_children():
            widget.destroy()
        self.play_btn.configure(state="disabled")
        self.refresh()


# ============================================================
#  SCREEN 5 - ENTER THE DUMMY'S HAND
# ============================================================
class DummyEntryScreen(ctk.CTkFrame):
    CARD_W, CARD_H = 50, 70

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=FELT_GREEN_DARK)
        self.controller = controller
        self.selected = set()
        self.excluded = set()  # cards already in the player's own hand - not eligible for dummy
        self.tiles = {}
        add_felt_background(self)

        self.header = ctk.CTkLabel(
            self, text="Enter the dummy's hand",
            font=ctk.CTkFont(family="Georgia", size=26, weight="bold"), text_color=GOLD,
        )
        self.header.pack(pady=(24, 4))

        self.counter_label = ctk.CTkLabel(
            self, text="0 / 13 selected", font=ctk.CTkFont(size=15), text_color=CREAM,
        )
        self.counter_label.pack(pady=(0, 16))

        grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        grid_frame.pack(pady=4)

        for row, suit in enumerate(SUITS):
            for col, rank in enumerate(RANKS):
                key = (rank, suit)
                tile = ctk.CTkCanvas(
                    grid_frame, width=self.CARD_W, height=self.CARD_H,
                    bg=FELT_GREEN_DARK, highlightthickness=0,
                )
                tile.grid(row=row, column=col, padx=3, pady=4)
                tile.bind("<Button-1>", lambda e, k=key: self.toggle_card(k))
                tile.bind("<Enter>", lambda e, k=key: self._render(k, hover=True))
                tile.bind("<Leave>", lambda e, k=key: self._render(k, hover=False))
                self.tiles[key] = tile
                self._render(key, hover=False)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=20)

        self.confirm_btn = ctk.CTkButton(
            btn_row, text="Confirm dummy's hand", state="disabled",
            fg_color=CARD_BACK, hover_color="#5c1620", text_color=CREAM,
            corner_radius=12, width=220, height=48,
            font=ctk.CTkFont(size=16, weight="bold"), command=self.confirm_hand,
        )
        self.confirm_btn.grid(row=0, column=0, padx=10)

        back_btn = ctk.CTkButton(
            btn_row, text="Back", fg_color="transparent",
            border_width=2, border_color=CREAM, text_color=CREAM,
            hover_color=FELT_GREEN, corner_radius=12, width=140, height=48,
            command=lambda: controller.show_frame("BiddingScreen"),
        )
        back_btn.grid(row=0, column=1, padx=10)

    def _render(self, key, hover):
        rank, suit = key
        tile = self.tiles[key]
        tile.delete("all")
        if key in self.excluded:
            draw_card_face(tile, 0, 0, rank, suit, w=self.CARD_W, h=self.CARD_H,
                            bg="#5a5a52", outline="#3f3f38", outline_w=1.2)
            return
        is_selected = key in self.selected
        if is_selected:
            bg = GOLD_HOVER if hover else GOLD
        else:
            bg = CREAM_HOVER if hover else CREAM
        draw_card_face(tile, 0, 0, rank, suit, w=self.CARD_W, h=self.CARD_H,
                        bg=bg, outline="#c9bd9a", outline_w=1.2)

    def toggle_card(self, key):
        if key in self.excluded:
            return  # already in your own hand - can't also be in the dummy
        if key in self.selected:
            self.selected.remove(key)
        else:
            if len(self.selected) >= 13:
                return
            self.selected.add(key)
        self._render(key, hover=True)
        self.counter_label.configure(text=f"{len(self.selected)} / 13 selected")
        self.confirm_btn.configure(state="normal" if len(self.selected) == 13 else "disabled")

    def confirm_hand(self):
        kind, seat = self.controller.pending_entry
        if kind == "dummy":
            self.controller.dummy_hand = list(self.selected)
        else:
            self.controller.north_hand = list(self.selected)
        self.controller.game_log.set_hand(seat, list(self.selected))
        self.controller.pending_entry = None
        self.controller.show_frame("PlayScreen")

    def on_show(self):
        self.selected.clear()
        self.excluded = set(self.controller.player_hand)
        if self.controller.dummy_hand and self.controller.pending_entry and self.controller.pending_entry[0] == "declarer":
            self.excluded |= set(self.controller.dummy_hand)
        for key in self.tiles:
            self._render(key, hover=False)
        self.counter_label.configure(text="0 / 13 selected")
        self.confirm_btn.configure(state="disabled")
        kind, seat = self.controller.pending_entry or ("dummy", self.controller.dummy_seat or "partner")
        if kind == "dummy":
            self.header.configure(text=f"Enter {seat.capitalize()}'s hand (the dummy)")
        else:
            self.header.configure(
                text=f"Enter {seat.capitalize()}'s hand (your partner is declaring - "
                     f"you'll get tips for their plays too)"
            )


# ============================================================
#  SCREEN 6 - CARD PLAY
# ============================================================
class PlayScreen(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=FELT_GREEN_DARK)
        self.controller = controller
        self.south_remaining = []
        self.dummy_remaining = []
        self.north_remaining = None  # only set when partner (North) is declaring
        self.leader = None
        self.declarer = None
        self.dummy_seat = None
        self.trump = None
        self.animating = False
        self.trick_count = 0
        self.current_suggestion_card = None

        add_felt_background(self)

        self.contract_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=15, weight="bold"), text_color=GOLD,
        )
        self.contract_label.pack(pady=(14, 2))

        self.status_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=14), text_color=CREAM,
        )
        self.status_label.pack(pady=(0, 2))

        self.suggestion_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=14, weight="bold"), text_color=GOLD_BRIGHT,
            wraplength=800, justify="center",
        )
        self.suggestion_label.pack(pady=(0, 6))

        table_row = ctk.CTkFrame(self, fg_color="transparent")
        table_row.pack(fill="both", expand=True, padx=16)

        self.canvas = ctk.CTkCanvas(table_row, bg=FELT_GREEN_DARK, highlightthickness=0, height=380)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._redraw())

        self.info_panel = ctk.CTkFrame(table_row, fg_color=PANEL_BG, corner_radius=12, width=340)
        self.info_panel.pack(side="right", fill="y", padx=(10, 0))
        self.info_panel.pack_propagate(False)
        ctk.CTkLabel(
            self.info_panel, text="What we can infer",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=GOLD, wraplength=310,
        ).pack(pady=(12, 6), padx=10)
        inference_scroll = ctk.CTkScrollableFrame(self.info_panel, fg_color="transparent")
        inference_scroll.pack(fill="both", expand=True, padx=6, pady=(0, 10))
        self.inference_label = ctk.CTkLabel(
            inference_scroll, text="", font=ctk.CTkFont(size=12), text_color=CREAM,
            wraplength=300, justify="left",
        )
        self.inference_label.pack(padx=6, pady=4, anchor="n")

        self.input_frame = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=12)
        self.input_frame.pack(pady=10, padx=16, fill="x")

        nav_row = ctk.CTkFrame(self, fg_color="transparent")
        nav_row.pack(pady=(0, 10))
        ctk.CTkButton(
            nav_row, text="New game", fg_color="transparent",
            border_width=2, border_color=CREAM, text_color=CREAM,
            hover_color=FELT_GREEN, corner_radius=10, width=140, height=34,
            command=lambda: controller.show_frame("WelcomeScreen"),
        ).pack(side="left", padx=6)

    # ---------------- setup ----------------
    def on_show(self):
        self.south_remaining = [(r, SUIT_SYMBOL[s]) for r, s in self.controller.player_hand]
        self.dummy_remaining = [(r, SUIT_SYMBOL[s]) for r, s in self.controller.dummy_hand]
        self.north_remaining = (
            [(r, SUIT_SYMBOL[s]) for r, s in self.controller.north_hand]
            if self.controller.north_hand else None
        )
        self.controller.tricks_won = {"NS": 0, "EW": 0}
        self.controller.played_cards = {s: [] for s in SEATS}
        self.controller.current_trick = []
        self.known_voids = {s: set() for s in SEATS}
        level, strain, declarer = self.controller.contract
        self.trump = None if strain == "NT" else strain
        self.declarer = declarer
        self.dummy_seat = self.controller.dummy_seat
        self.leader = play.opening_leader(declarer)
        self.animating = False
        self.trick_count = 0
        self._update_contract_label()
        self._redraw()
        self._update_input_panel()
        self._update_inference_panel()

    def _update_inference_panel(self):
        original_south = [(r, SUIT_SYMBOL[s]) for r, s in self.controller.player_hand]
        original_dummy = [(r, SUIT_SYMBOL[s]) for r, s in self.controller.dummy_hand]
        original_north = (
            [(r, SUIT_SYMBOL[s]) for r, s in self.controller.north_hand]
            if self.controller.north_hand else []
        )
        all_known_cards = original_south + original_dummy + original_north

        known_seats = {"south", self.dummy_seat}
        if self.north_remaining is not None:
            known_seats.add("north")
        hidden_seats = [s for s in SEATS if s not in known_seats]
        partner_hidden = "north" in hidden_seats

        def hcp_of(cards):
            return sum(engine.RANK_VALUES.get(r, 0) for r, _ in cards)

        known_hcp = hcp_of(all_known_cards)
        pool_hcp = 40 - known_hcp

        lines = []
        if partner_hidden:
            pmin, pmax, psuits = engine.infer_partner_profile(self.controller.auction, "north")
            opp_min = max(0, pool_hcp - pmax)
            opp_max = min(pool_hcp, pool_hcp - pmin)
            lines.append(f"Opponents: ~{opp_min}-{opp_max} HCP combined (partner's bidding suggests ~{pmin}-{pmax}).")
        else:
            lines.append(f"Opponents hold exactly {pool_hcp} HCP combined (both their hands unseen).")

        lines.append("")
        for suit_key in SUITS:
            suit_sym = SUIT_SYMBOL[suit_key]
            total_known = sum(1 for _, s in all_known_cards if s == suit_sym)
            played_hidden = sum(
                1 for seat in hidden_seats for (_, s) in self.controller.played_cards[seat] if s == suit_sym
            )
            unseen = 13 - total_known - played_hidden
            if partner_hidden:
                p_min_len = psuits.get(suit_sym, 0)
                opp_max_len = max(0, unseen - p_min_len)
                note = ""
                if unseen > 0 and p_min_len >= max(unseen - 1, 1):
                    note = " - opponents likely short"
                lines.append(f"{suit_sym}: {unseen} unseen (partner {p_min_len}+, opponents ≤{opp_max_len}{note})")
            else:
                lines.append(f"{suit_sym}: opponents hold {unseen} between them")

        void_lines = []
        for seat in hidden_seats:
            suits_void = self.known_voids.get(seat, set())
            if suits_void:
                void_lines.append(f"{seat.capitalize()} is void in: {', '.join(sorted(suits_void))}")
        if void_lines:
            lines.append("")
            lines.extend(void_lines)

        lines.append("")
        lines.append("Cards played so far:")
        played_by_suit = {suit_sym: [] for suit_sym in SUIT_SYMBOL.values()}
        for seat in SEATS:
            for rank, suit_sym in self.controller.played_cards[seat]:
                played_by_suit[suit_sym].append(rank)
        for seat, (rank, suit_sym) in self.controller.current_trick:
            played_by_suit[suit_sym].append(rank)
        for suit_key in SUITS:
            suit_sym = SUIT_SYMBOL[suit_key]
            ranks = played_by_suit[suit_sym]
            if ranks:
                ranks_sorted = sorted(ranks, key=lambda r: -RANK_ORDER[r])
                lines.append(f"{suit_sym}: {' '.join(ranks_sorted)}")
            else:
                lines.append(f"{suit_sym}: none yet")

        self.inference_label.configure(text="\n".join(lines))

    def _update_contract_label(self):
        level, strain, declarer = self.controller.contract
        needed = play.tricks_needed_for_contract(level)
        declarer_side = play.partnership_of(declarer)
        other_side = "EW" if declarer_side == "NS" else "NS"
        won = self.controller.tricks_won
        defeated_at = 14 - needed
        if won[declarer_side] >= needed:
            status = f"Contract made! {declarer_side} took {won[declarer_side]} tricks (needed {needed})."
        elif won[other_side] >= defeated_at:
            status = f"Contract defeated - {other_side} has taken {won[other_side]} tricks."
        else:
            status = (
                f"{declarer_side}: {won[declarer_side]}/{needed} tricks needed  |  "
                f"{other_side}: {won[other_side]}/{defeated_at} to defeat"
            )
        self.contract_label.configure(
            text=f"Contract: {level}{strain} by {declarer.capitalize()}  —  {status}"
        )

    # ---------------- geometry / drawing ----------------
    def _seat_positions(self, w, h):
        return {
            "north": (w * 0.5, h * 0.20),
            "west": (w * 0.16, h * 0.5),
            "east": (w * 0.84, h * 0.5),
            "south": (w * 0.5, h * 0.80),
        }

    def _trick_slots(self, w, h):
        return {
            "north": (w * 0.5, h * 0.40),
            "south": (w * 0.5, h * 0.60),
            "west": (w * 0.40, h * 0.5),
            "east": (w * 0.60, h * 0.5),
        }

    def _draw_known_hand(self, cards, cx, cy, label):
        card_w, card_h = 42, 60
        ordered = sorted(cards, key=lambda c: (SUIT_ORDER[SYMBOL_TO_SUITKEY[c[1]]], -RANK_ORDER[c[0]]))
        total_w = len(ordered) * (card_w - 10) + 10 if ordered else 0
        start_x = cx - total_w / 2
        y = cy - card_h / 2
        self.canvas.create_text(cx, cy - card_h / 2 - 16, text=label, fill=CREAM, font=SEAT_FONT)
        for i, (rank, suit_sym) in enumerate(ordered):
            x = start_x + i * (card_w - 10)
            draw_card_face(self.canvas, x, y, rank, SYMBOL_TO_SUITKEY[suit_sym], w=card_w, h=card_h)

    def _draw_hidden_fan(self, seat, cx, cy, n):
        orientation = "horizontal" if seat == "north" else "vertical"
        for i in range(n):
            t = (i - (n - 1) / 2) / max((n - 1) / 2, 1) if n > 1 else 0
            if orientation == "horizontal":
                angle = t * 22
                x = cx + t * 90
                y = cy + abs(t) * 9
            else:
                base = 90 if seat == "west" else -90
                angle = base + t * 22
                y = cy + t * 80
                x = cx + (abs(t) * 8 if seat == "west" else -abs(t) * 8)
            draw_card_back(self.canvas, x, y, angle, w=30, h=42)
        label_color = CREAM
        if orientation == "horizontal":
            self.canvas.create_text(cx, cy - 36, text=seat.capitalize(), fill=label_color, font=SEAT_FONT)
        else:
            label_x = cx - 40 if seat == "west" else cx + 40
            self.canvas.create_text(label_x, cy, text=seat.capitalize(), fill=label_color, font=SEAT_FONT)

    def _redraw(self):
        if self.animating:
            return
        self.canvas.delete("all")
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            return
        draw_diamond_texture(self.canvas, w, h)
        margin_x, margin_y = w * 0.10, h * 0.28
        self.canvas.create_oval(margin_x, margin_y, w - margin_x, h - margin_y,
                                 fill=FELT_GREEN, outline=GOLD, width=3)

        positions = self._seat_positions(w, h)
        for seat in SEATS:
            cx, cy = positions[seat]
            if seat == "south":
                self._draw_known_hand(self.south_remaining, cx, cy, "You (South)")
            elif seat == self.dummy_seat:
                self._draw_known_hand(self.dummy_remaining, cx, cy, f"{seat.capitalize()} (dummy)")
            elif seat == "north" and self.north_remaining is not None:
                self._draw_known_hand(self.north_remaining, cx, cy, "North (you play this too)")
            else:
                remaining = 13 - len(self.controller.played_cards[seat])
                self._draw_hidden_fan(seat, cx, cy, remaining)

        slots = self._trick_slots(w, h)
        for seat, card in self.controller.current_trick:
            x, y = slots[seat]
            rank, suit_sym = card
            draw_card_face(self.canvas, x - 21, y - 30, rank, SYMBOL_TO_SUITKEY[suit_sym],
                            w=42, h=60, tags=(f"trickcard_{seat}",))

    # ---------------- turn logic ----------------
    def _acting_seat(self):
        n = len(self.controller.current_trick)
        if n >= 4:
            return None
        return SEATS[(SEATS.index(self.leader) + n) % 4]

    def _hand_for_seat(self, seat):
        if seat == "south":
            return self.south_remaining
        if seat == self.dummy_seat:
            return self.dummy_remaining
        if seat == "north" and self.north_remaining is not None:
            return self.north_remaining
        return None

    def _controls(self, seat):
        if seat == "south":
            return True
        if seat == self.dummy_seat and self.declarer == "south":
            return True
        if seat == "north" and self.declarer == "north" and self.north_remaining is not None:
            return True
        return False

    def _update_input_panel(self):
        for w in self.input_frame.winfo_children():
            w.destroy()
        self._update_inference_panel()

        seat = self._acting_seat()
        if seat is None:
            return
        self.status_label.configure(text=f"{seat.capitalize()} to play.")

        hand = self._hand_for_seat(seat)
        if hand is not None:
            controls = self._controls(seat)
            suggestion_card = None
            if controls and hand:
                is_declaring_side = play.partnership_of(seat) == play.partnership_of(self.declarer)
                suggestion_card, why = play.suggest_card(
                    hand, self.controller.current_trick, self.trump, seat,
                    is_declaring_side, self.known_voids,
                )
                self.current_suggestion_card = suggestion_card
                if suggestion_card:
                    self.suggestion_label.configure(
                        text=f"Suggested: {suggestion_card[0]}{suggestion_card[1]}  —  {why}"
                    )
            else:
                self.current_suggestion_card = None
                self.suggestion_label.configure(text=f"Enter which card {seat.capitalize()} played.")

            row = ctk.CTkFrame(self.input_frame, fg_color="transparent")
            row.pack(pady=10)
            ordered = sorted(hand, key=lambda c: (SUIT_ORDER[SYMBOL_TO_SUITKEY[c[1]]], -RANK_ORDER[c[0]]))
            for card in ordered:
                tile = ctk.CTkCanvas(row, width=46, height=64, bg=PANEL_BG, highlightthickness=0)
                tile.pack(side="left", padx=2)
                bg = GOLD if card == suggestion_card else CREAM
                draw_card_face(tile, 0, 0, card[0], SYMBOL_TO_SUITKEY[card[1]], w=46, h=64, bg=bg)
                tile.bind("<Button-1>", lambda e, c=card, s=seat: self._play_card(s, c))
        else:
            self.current_suggestion_card = None
            self.suggestion_label.configure(text=f"Enter which card {seat.capitalize()} played.")
            played_all = [c for s in SEATS for c in self.controller.played_cards[s]]
            unavailable = set(self.south_remaining) | set(self.dummy_remaining) | set(played_all)
            if self.north_remaining is not None:
                unavailable |= set(self.north_remaining)

            grid = ctk.CTkFrame(self.input_frame, fg_color="transparent")
            grid.pack(pady=10)
            for row_i, suit_key in enumerate(SUITS):
                suit_sym = SUIT_SYMBOL[suit_key]
                for col_i, rank in enumerate(RANKS):
                    card = (rank, suit_sym)
                    if card in unavailable:
                        continue
                    tile = ctk.CTkCanvas(grid, width=38, height=54, bg=PANEL_BG, highlightthickness=0)
                    tile.grid(row=row_i, column=col_i, padx=2, pady=2)
                    draw_card_face(tile, 0, 0, rank, suit_key, w=38, h=54, bg=CREAM)
                    tile.bind("<Button-1>", lambda e, c=card, s=seat: self._play_card(s, c))

    def _play_card(self, seat, card):
        if self.animating:
            return
        if not self.controller.current_trick:
            self.controller.game_log.start_trick(self.trick_count + 1, seat)
        else:
            led_suit = self.controller.current_trick[0][1][1]
            if card[1] != led_suit:
                self.known_voids[seat].add(led_suit)
        self.controller.game_log.log_card(seat, card, self.current_suggestion_card)
        self.controller.current_trick.append((seat, card))
        self.controller.played_cards[seat].append(card)
        hand = self._hand_for_seat(seat)
        if hand is not None and card in hand:
            hand.remove(card)

        self._redraw()
        if len(self.controller.current_trick) == 4:
            self._animate_trick_completion()
        else:
            self._update_input_panel()

    # ---------------- trick-winner animation ----------------
    def _animate_trick_completion(self):
        trick = list(self.controller.current_trick)
        winner = play.trick_winner(trick, self.trump)
        self.animating = True
        for w_widget in self.input_frame.winfo_children():
            w_widget.destroy()
        self.status_label.configure(text=f"{winner.capitalize()} wins the trick!")
        self.suggestion_label.configure(text="")

        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        target = self._seat_positions(w, h)[winner]
        slots = self._trick_slots(w, h)
        steps = 12

        def step(i=0):
            if i >= steps:
                partnership = play.partnership_of(winner)
                self.controller.tricks_won[partnership] += 1
                self.controller.game_log.finish_trick(winner)
                self.trick_count += 1
                self.controller.current_trick = []
                self.leader = winner
                self.animating = False
                self._update_contract_label()
                self._redraw()
                self._update_input_panel()
                self._maybe_finalize_game_log()
                return
            for seat, _ in trick:
                start = slots[seat]
                dx = (target[0] - start[0]) / steps
                dy = (target[1] - start[1]) / steps
                self.canvas.move(f"trickcard_{seat}", dx, dy)
            self.after(25, lambda: step(i + 1))

        step()

    def _maybe_finalize_game_log(self):
        total_played = sum(len(self.controller.played_cards[s]) for s in SEATS)
        if total_played < 52:
            return
        # Fill in the two hands we never explicitly asked for - by the end
        # of a complete deal, everything a hidden seat played over all 13
        # tricks IS their entire original hand.
        for seat in SEATS:
            if self.controller.game_log.data["hands"][seat] is None:
                self.controller.game_log.set_hand(seat, self.controller.played_cards[seat])

        level, strain, declarer = self.controller.contract
        declarer_side = play.partnership_of(declarer)
        other_side = "EW" if declarer_side == "NS" else "NS"
        needed = play.tricks_needed_for_contract(level)
        won = self.controller.tricks_won
        if won[declarer_side] >= needed:
            outcome = f"made by {won[declarer_side] - needed} overtrick(s)" if won[declarer_side] > needed else "made exactly"
        else:
            outcome = f"down {needed - won[declarer_side]}"
        self.controller.game_log.set_result(won, outcome)
        self.controller.game_log.finalize("completed")


if __name__ == "__main__":
    app = BridgeCheaterApp()
    app.mainloop()