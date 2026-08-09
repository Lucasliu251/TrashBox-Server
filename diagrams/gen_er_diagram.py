"""Generate ER diagram for TrashBox-Server database."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# Use a CJK-capable font
_CJK = "PingFang HK"
fm.fontManager.addfont(
    next(f.fname for f in fm.fontManager.ttflist if f.name == _CJK)
)
plt.rcParams["font.family"] = _CJK
plt.rcParams["axes.unicode_minus"] = False
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

# ── Layout config ──────────────────────────────────────────────
FIG_W, FIG_H = 22, 16
TABLE_W = 3.2
HEADER_H = 0.45
ROW_H = 0.30
PK_COLOR = "#FFF3E0"
FK_COLOR = "#E3F2FD"
NORMAL_COLOR = "#FAFAFA"
HEADER_COLOR = "#1565C0"
HEADER_TEXT = "white"
WEEKLY_BG = "#FFF8E1"
STANDALONE_BORDER = "#FF8F00"
REL_COLOR = "#546E7A"
IMPLICIT_COLOR = "#9E9E9E"
DASH_STYLE = (0, (5, 3))

# ── Table definitions ──────────────────────────────────────────
tables = {
    "users": {
        "pos": (1.0, 10.0),
        "fields": [
            ("PK", "uuid", "VARCHAR", "微信OpenID"),
            ("  ", "steam_id", "VARCHAR", "SteamID64"),
            ("  ", "auth_code", "VARCHAR", "授权码"),
            ("  ", "match_code", "VARCHAR", "匹配码"),
            ("  ", "nickname", "VARCHAR", "昵称"),
            ("  ", "avatar", "VARCHAR", "头像路径"),
            ("  ", "canEdit", "TINYINT", "可编辑标志"),
            ("  ", "created_at", "DATETIME", "创建时间"),
            ("  ", "updated_at", "DATETIME", "更新时间"),
        ],
    },
    "daily": {
        "pos": (6.5, 10.0),
        "fields": [
            ("PK", "steam_id", "VARCHAR", "SteamID64"),
            ("PK", "record_date", "DATE", "记录日期"),
            ("  ", "nickname", "VARCHAR", "昵称"),
            ("  ", "total_kills", "INT", "累计击杀"),
            ("  ", "total_deaths", "INT", "累计死亡"),
            ("  ", "total_mvps", "INT", "累计MVP"),
            ("  ", "total_HS", "INT", "累计爆头"),
            ("  ", "total_damage", "INT", "累计伤害"),
            ("  ", "total_rounds_played", "INT", "累计回合"),
            ("  ", "total_wins", "INT", "累计胜利"),
            ("  ", "total_time_played", "BIGINT", "累计时长"),
            ("  ", "total_money_earned", "BIGINT", "累计金钱"),
            ("  ", "style_tag", "VARCHAR", "风格标签"),
        ],
    },
    "weekly": {
        "pos": (12.5, 10.0),
        "standalone": True,
        "fields": [
            ("PK", "steam_id", "VARCHAR", "SteamID64"),
            ("PK", "week_start", "DATE", "周起始日"),
            ("  ", "nickname", "VARCHAR", "昵称"),
            ("  ", "kills", "INT", "周击杀"),
            ("  ", "deaths", "INT", "周死亡"),
            ("  ", "mvps", "INT", "周MVP"),
            ("  ", "headshots", "INT", "周爆头"),
            ("  ", "damage", "INT", "周伤害"),
            ("  ", "rounds_played", "INT", "周回合"),
            ("  ", "wins", "INT", "周胜利"),
            ("  ", "rating", "FLOAT", "周Rating"),
            ("  ", "style_tag", "VARCHAR", "风格标签"),
        ],
    },
    "posts": {
        "pos": (1.0, 4.5),
        "fields": [
            ("PK", "id", "INT AI", "自增主键"),
            ("FK", "uuid", "VARCHAR", "→ users.uuid"),
            ("  ", "title", "VARCHAR", "标题"),
            ("  ", "content", "LONGTEXT", "HTML内容"),
            ("  ", "tag", "VARCHAR", "标签"),
            ("  ", "views", "INT", "浏览量"),
            ("  ", "created_at", "DATETIME", "创建时间"),
        ],
    },
    "comments": {
        "pos": (6.5, 4.5),
        "fields": [
            ("PK", "id", "INT AI", "自增主键"),
            ("FK", "post_id", "INT", "→ posts.id"),
            ("FK", "uuid", "VARCHAR", "→ users.uuid"),
            ("  ", "content", "TEXT", "评论内容"),
            ("  ", "created_at", "DATETIME", "创建时间"),
        ],
    },
    "subscriptions": {
        "pos": (12.5, 4.5),
        "fields": [
            ("PK", "openid", "VARCHAR", "→ users.uuid"),
            ("PK", "template_id", "VARCHAR", "消息模板ID"),
            ("  ", "remaining_count", "INT", "剩余推送次数"),
        ],
    },
    "server_avg_stats": {
        "pos": (17.5, 10.0),
        "standalone": True,
        "fields": [
            ("PK", "date", "DATE", "日期"),
            ("  ", "avg_kpr", "FLOAT", "场均击杀率"),
            ("  ", "avg_spr", "FLOAT", "场均存活率"),
            ("  ", "avg_adr", "FLOAT", "场均ADR"),
            ("  ", "avg_hsr", "FLOAT", "场均爆头率"),
            ("  ", "avg_mpr", "FLOAT", "场均MVP率"),
            ("  ", "avg_wr", "FLOAT", "场均胜率"),
            ("  ", "active_players", "INT", "活跃玩家数"),
        ],
    },
    "friends": {
        "pos": (17.5, 4.5),
        "fields": [
            ("PK", "id", "INT AI", "自增主键"),
            ("FK", "uuid", "VARCHAR", "→ users.uuid"),
            ("FK", "friend_uuid", "VARCHAR", "→ users.uuid"),
            ("  ", "status", "TINYINT", "0申请 1接受"),
            ("  ", "created_at", "DATETIME", "申请时间"),
        ],
    },
}

# ── Relationship definitions ───────────────────────────────────
# (from_table, from_field, to_table, to_field, label, is_implicit)
relationships = [
    ("posts", "uuid", "users", "uuid", "1:N", False),
    ("comments", "post_id", "posts", "id", "1:N", False),
    ("comments", "uuid", "users", "uuid", "1:N", False),
    ("subscriptions", "openid", "users", "uuid", "1:N", False),
    ("friends", "uuid", "users", "uuid", "1:N", False),
    ("friends", "friend_uuid", "users", "uuid", "1:N", False),
    ("daily", "steam_id", "users", "steam_id", "1:N", True),
    ("weekly", "steam_id", "users", "steam_id", "1:N", True),
]


# ── Drawing helpers ────────────────────────────────────────────
def field_bg(tag):
    if "PK" in tag:
        return PK_COLOR
    if "FK" in tag:
        return FK_COLOR
    return NORMAL_COLOR


def draw_table(ax, name, info):
    x0, y0 = info["pos"]
    standalone = info.get("standalone", False)
    fields = info["fields"]
    n_rows = len(fields)
    total_h = HEADER_H + n_rows * ROW_H

    # Shadow
    shadow = FancyBboxPatch(
        (x0 + 0.04, y0 - total_h - 0.04), TABLE_W, total_h,
        boxstyle="round,pad=0.06", facecolor="#E0E0E0", edgecolor="none", zorder=1,
    )
    ax.add_patch(shadow)

    # Border color
    edge = STANDALONE_BORDER if standalone else "#424242"
    lw = 2.0 if standalone else 1.2

    # Body background
    body = FancyBboxPatch(
        (x0, y0 - total_h), TABLE_W, total_h,
        boxstyle="round,pad=0.06", facecolor="white", edgecolor=edge, linewidth=lw, zorder=2,
    )
    ax.add_patch(body)

    # Header
    header = FancyBboxPatch(
        (x0, y0 - HEADER_H), TABLE_W, HEADER_H,
        boxstyle="round,pad=0.06", facecolor=HEADER_COLOR, edgecolor=HEADER_COLOR, zorder=3,
    )
    ax.add_patch(header)
    ax.text(
        x0 + TABLE_W / 2, y0 - HEADER_H / 2, name,
        ha="center", va="center", fontsize=12, fontweight="bold",
        color=HEADER_TEXT, zorder=4,
    )

    # Standalone label
    if standalone:
        ax.text(
            x0 + TABLE_W, y0 + 0.15, "独立表（无FK）",
            ha="right", va="bottom", fontsize=8, color=STANDALONE_BORDER,
            fontstyle="italic", zorder=4,
        )

    # Rows
    for i, (tag, fname, ftype, desc) in enumerate(fields):
        ry = y0 - HEADER_H - (i + 1) * ROW_H
        bg = field_bg(tag)
        rect = matplotlib.patches.Rectangle(
            (x0 + 0.01, ry), TABLE_W - 0.02, ROW_H,
            facecolor=bg, edgecolor="none", zorder=3,
        )
        ax.add_patch(rect)
        ax.text(x0 + 0.12, ry + ROW_H / 2, f"{tag} {fname}", fontsize=7.5, va="center", zorder=4, fontfamily="monospace")
        ax.text(x0 + TABLE_W - 0.12, ry + ROW_H / 2, ftype, fontsize=7, va="center", ha="right", zorder=4, color="#757575", fontfamily="monospace")

    # Separator lines
    for i in range(n_rows):
        ly = y0 - HEADER_H - (i + 1) * ROW_H
        ax.plot([x0 + 0.08, x0 + TABLE_W - 0.08], [ly, ly], color="#E0E0E0", lw=0.5, zorder=3)

    # Return connection anchor points
    cx = x0 + TABLE_W / 2
    top = y0
    bot = y0 - total_h
    left_mid = (x0, y0 - total_h / 2)
    right_mid = (x0 + TABLE_W, y0 - total_h / 2)
    return {"top": (cx, top), "bot": (cx, bot), "left": left_mid, "right": right_mid, "x0": x0, "y0": y0, "total_h": total_h}


def get_field_anchor(pos_info, field_idx, side="left"):
    """Get the y-coordinate of a specific field row on a given side."""
    x0, y0 = pos_info["x0"], pos_info["y0"]
    ry = y0 - HEADER_H - (field_idx + 0.5) * ROW_H
    if side == "left":
        return (x0, ry)
    return (x0 + TABLE_W, ry)


# ── Main rendering ─────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
ax.set_xlim(-0.5, 22)
ax.set_ylim(1, 15.5)
ax.set_aspect("equal")
ax.axis("off")
fig.patch.set_facecolor("white")

# Title
ax.text(11, 15.0, "TrashBox 数据库 ER 关系图", ha="center", va="center",
        fontsize=20, fontweight="bold", color="#212121")
ax.text(11, 14.5, "Database Entity-Relationship Diagram", ha="center", va="center",
        fontsize=11, color="#9E9E9E")

# Draw all tables
anchors = {}
for name, info in tables.items():
    anchors[name] = draw_table(ax, name, info)

# ── Draw relationships ─────────────────────────────────────────
def draw_rel(ax, from_pt, to_pt, label, is_implicit=False):
    color = IMPLICIT_COLOR if is_implicit else REL_COLOR
    ls = DASH_STYLE if is_implicit else "-"
    arrow = FancyArrowPatch(
        from_pt, to_pt,
        arrowstyle="-|>",
        connectionstyle="arc3,rad=0.12",
        color=color, linewidth=1.4, linestyle=ls,
        mutation_scale=12, zorder=5,
    )
    ax.add_patch(arrow)
    mx = (from_pt[0] + to_pt[0]) / 2
    my = (from_pt[1] + to_pt[1]) / 2
    ax.text(mx, my + 0.18, label, fontsize=8, ha="center", va="bottom",
            color=color, fontweight="bold", zorder=6,
            bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor=color, linewidth=0.6))


# posts.uuid -> users.uuid
draw_rel(ax, anchors["posts"]["right"], anchors["users"]["left"], "1 : N")
# comments.post_id -> posts.id
draw_rel(ax, anchors["comments"]["left"], anchors["posts"]["right"], "1 : N")
# comments.uuid -> users.uuid
draw_rel(ax,
         (anchors["comments"]["left"][0], anchors["comments"]["left"][1] + 0.3),
         (anchors["users"]["right"][0], anchors["users"]["right"][1] + 0.3),
         "1 : N")
# subscriptions.openid -> users.uuid
draw_rel(ax, anchors["subscriptions"]["left"],
         (anchors["users"]["right"][0], anchors["users"]["right"][1] - 0.8),
         "1 : N")
# friends.uuid -> users.uuid
draw_rel(ax, anchors["friends"]["left"],
         (anchors["users"]["right"][0], anchors["users"]["right"][1] - 1.6),
         "1 : N")
# friends.friend_uuid -> users.uuid
draw_rel(ax,
         (anchors["friends"]["left"][0], anchors["friends"]["left"][1] - 0.3),
         (anchors["users"]["right"][0], anchors["users"]["right"][1] - 2.0),
         "1 : N")
# daily.steam_id <-> users.steam_id (implicit)
draw_rel(ax, anchors["daily"]["left"], anchors["users"]["right"], "1 : N (隐式)", is_implicit=True)
# weekly.steam_id <-> users.steam_id (implicit)
draw_rel(ax, anchors["weekly"]["left"], anchors["daily"]["right"], "1 : N (隐式)", is_implicit=True)

# ── Legend ──────────────────────────────────────────────────────
legend_x, legend_y = 0.5, 2.5
ax.text(legend_x, legend_y, "图例", fontsize=11, fontweight="bold", color="#424242")

legend_items = [
    (PK_COLOR, "PK  主键字段"),
    (FK_COLOR, "FK  外键字段"),
    (NORMAL_COLOR, "      普通字段"),
]
for i, (color, text) in enumerate(legend_items):
    ry = legend_y - 0.45 - i * 0.38
    rect = matplotlib.patches.Rectangle((legend_x, ry), 0.3, 0.26, facecolor=color, edgecolor="#BDBDBD", linewidth=0.8)
    ax.add_patch(rect)
    ax.text(legend_x + 0.45, ry + 0.13, text, fontsize=9, va="center", color="#424242")

# Implicit FK legend
ry_impl = legend_y - 0.45 - 3 * 0.38
ax.plot([legend_x, legend_x + 0.3], [ry_impl + 0.13, ry_impl + 0.13], color=IMPLICIT_COLOR, ls=DASH_STYLE, lw=1.4)
ax.text(legend_x + 0.45, ry_impl + 0.13, "隐式外键（逻辑关联，无SQL FK约束）", fontsize=9, va="center", color=IMPLICIT_COLOR)

# Standalone border
ry_sa = legend_y - 0.45 - 4 * 0.38
rect_sa = matplotlib.patches.Rectangle((legend_x, ry_sa), 0.3, 0.26, facecolor="white", edgecolor=STANDALONE_BORDER, linewidth=2)
ax.add_patch(rect_sa)
ax.text(legend_x + 0.45, ry_sa + 0.13, "独立表（无外键依赖）", fontsize=9, va="center", color=STANDALONE_BORDER)

plt.tight_layout()
out = "/Users/lucas/Develop/project/TrashBox-Server/diagrams/fig_er_diagram.png"
fig.savefig(out, dpi=180, bbox_inches="tight", facecolor="white")
print(f"Saved to {out}")
