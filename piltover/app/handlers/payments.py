from __future__ import annotations

import json
import random
from pathlib import Path
from time import time

from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import StarsAmount, StarsGiftOption, StarsGiveawayOption, TLObjectVector
from piltover.tl.functions import (
    DocumentAttributeAnimated, DocumentAttributeSticker, InputStickerSetEmpty,
    StarGiftAttributeModel, StarGiftAttributeRarity,
)
from piltover.tl.functions.payments import (
    SavedStarGifts, StarGiftWithdrawalUrl, ResaleStarGifts,
    StarGiftCollectionsNotModified,
    CheckCanSendGiftResultOk,
    StarGiftAuctionState, StarGiftAuctionAcquiredGifts,
    StarGiftActiveAuctionsNotModified, StarGiftUpgradeAttributes,
    StarGiftsNotModified,
    GetStarGifts, GetStarGiftUpgradePreview, GetUniqueStarGift,
    GetSavedStarGifts, GetSavedStarGift, GetStarGiftWithdrawalUrl,
    GetResaleStarGifts, GetStarGiftCollections, GetUniqueStarGiftValueInfo,
    CheckCanSendGift, GetStarGiftAuctionState, GetStarGiftAuctionAcquiredGifts,
    GetStarGiftActiveAuctions, GetStarGiftUpgradeAttributes,
    GetStarsGiftOptions, GetStarsGiveawayOptions,
    SaveStarGift, ConvertStarGift, UpgradeStarGift, TransferStarGift,
    ToggleChatStarGiftNotifications, ToggleStarGiftsPinnedToTop,
    UpdateStarGiftPrice, CreateStarGiftCollection, UpdateStarGiftCollection,
    ReorderStarGiftCollections, DeleteStarGiftCollection,
    ResolveStarGiftOffer, SendStarGiftOffer,
    GetCraftStarGifts, CraftStarGift,
    GetConnectedStarRefBots, GetConnectedStarRefBot,
    GetSuggestedStarRefBots, ConnectStarRefBot, EditConnectedStarRefBot,
    ConnectedStarRefBots, SuggestedStarRefBots,
)
from piltover.tl.types.payments import StarGifts_189, StarGiftUpgradePreview_196, UniqueStarGift_197
from piltover.tl.types._root import StarGift_196
from piltover.worker import MessageHandler

handler = MessageHandler("payments")

NOAUTH = ReqHandlerFlags.AUTH_NOT_REQUIRED

MINI_PASHA_GIFT_ID   = 1_000_001
MINI_PASHA_STARS     = 410
MINI_PASHA_CONVERT   = 50
MINI_PASHA_UPGRADE   = 1000
# 25% per craft variant (4 variants × 25% = 100% total)
CRAFT_CHANCE_EACH    = 0.25

_CFG_PATH = Path("data/mini_pasha_gift.json")


def _cfg() -> dict | None:
    return json.loads(_CFG_PATH.read_text()) if _CFG_PATH.exists() else None


async def _file(fid: int):
    from piltover.db.models import File
    return await File.get_or_none(id=fid)


async def _mini_pasha_gift() -> StarGift_196 | None:
    cfg = _cfg()
    if not cfg:
        return None
    f = await _file(cfg["base_file_id"])
    if not f:
        return None
    return StarGift_196(
        id=MINI_PASHA_GIFT_ID,
        sticker=f.to_tl_document(),
        stars=MINI_PASHA_STARS,
        convert_stars=MINI_PASHA_CONVERT,
        upgrade_stars=MINI_PASHA_UPGRADE,
    )


async def _variant_attrs(key: str) -> list:
    cfg = _cfg()
    if not cfg:
        return []
    rarity = StarGiftAttributeRarity(permille=250)  # 25%
    attrs = []
    for i, fid in enumerate(cfg.get(key, [])):
        f = await _file(fid)
        if f:
            attrs.append(StarGiftAttributeModel(
                name=f"Mini Pasha #{i + 1}",
                document=f.to_tl_document(),
                rarity=rarity,
            ))
    return attrs


# ── Catalogue ─────────────────────────────────────────────────────────────────

@handler.on_request(GetStarGifts, NOAUTH)
async def get_star_gifts():
    gift = await _mini_pasha_gift()
    if gift is None:
        return StarGiftsNotModified()
    return StarGifts_189(hash=0, gifts=[gift], chats=[], users=[])


@handler.on_request(GetStarGiftUpgradePreview, NOAUTH)
async def get_star_gift_upgrade_preview():
    attrs = await _variant_attrs("variant_file_ids")
    return StarGiftUpgradePreview_196(sample_attributes=attrs, prices=[], next_prices=[])


@handler.on_request(GetUniqueStarGift, NOAUTH)
async def get_unique_star_gift():
    return UniqueStarGift_197(gift=None, users=[], chats=[])


# ── Saved gifts ───────────────────────────────────────────────────────────────

@handler.on_request(GetSavedStarGifts, NOAUTH)
async def get_saved_star_gifts():
    return SavedStarGifts(count=0, gifts=[], chats=[], users=[])


@handler.on_request(GetSavedStarGift, NOAUTH)
async def get_saved_star_gift():
    return SavedStarGifts(count=0, gifts=[], chats=[], users=[])


@handler.on_request(GetCraftStarGifts, NOAUTH)
async def get_craft_star_gifts():
    return SavedStarGifts(count=0, gifts=[], chats=[], users=[])


@handler.on_request(SaveStarGift, NOAUTH)
async def save_star_gift(): return True

@handler.on_request(ConvertStarGift, NOAUTH)
async def convert_star_gift(): return True

@handler.on_request(UpgradeStarGift, NOAUTH)
async def upgrade_star_gift(): return True

@handler.on_request(TransferStarGift, NOAUTH)
async def transfer_star_gift(): return True

@handler.on_request(UpdateStarGiftPrice, NOAUTH)
async def update_star_gift_price(): return True

@handler.on_request(ToggleChatStarGiftNotifications, NOAUTH)
async def toggle_chat_star_gift_notifications(): return True

@handler.on_request(ToggleStarGiftsPinnedToTop, NOAUTH)
async def toggle_star_gifts_pinned_to_top(): return True


# ── Craft ─────────────────────────────────────────────────────────────────────

@handler.on_request(CraftStarGift, NOAUTH)
async def craft_star_gift(request: CraftStarGift):
    """
    Accept 1–4 upgraded Mini Pasha gifts.
    Each of the 4 craft-result models has 25% drop chance.
    Returns the crafted gift document (or True if none dropped).
    """
    gifts = request.stargift
    if not (1 <= len(gifts) <= 4):
        raise ErrorRpc(error_code=400, error_message="STARGIFT_CRAFT_COUNT_INVALID")

    craft_attrs = await _variant_attrs("craft_file_ids")
    if not craft_attrs:
        return True

    # Each variant: 25% independent chance
    for attr in craft_attrs:
        if random.random() < CRAFT_CHANCE_EACH:
            # In a full impl: create SavedStarGift record and push update.
            # Here we return True to signal success; client will re-fetch.
            return True

    return True  # no drop this time


# ── Resale ────────────────────────────────────────────────────────────────────

@handler.on_request(GetResaleStarGifts, NOAUTH)
async def get_resale_star_gifts():
    return ResaleStarGifts(count=0, gifts=[], chats=[], users=[])


# ── Withdrawal ────────────────────────────────────────────────────────────────

@handler.on_request(GetStarGiftWithdrawalUrl, NOAUTH)
async def get_star_gift_withdrawal_url():
    return StarGiftWithdrawalUrl(url="https://fragment.com/")


# ── Collections ───────────────────────────────────────────────────────────────

@handler.on_request(GetStarGiftCollections, NOAUTH)
async def get_star_gift_collections():
    return StarGiftCollectionsNotModified()

@handler.on_request(CreateStarGiftCollection, NOAUTH)
async def create_star_gift_collection(): return True

@handler.on_request(UpdateStarGiftCollection, NOAUTH)
async def update_star_gift_collection(): return True

@handler.on_request(ReorderStarGiftCollections, NOAUTH)
async def reorder_star_gift_collections(): return True

@handler.on_request(DeleteStarGiftCollection, NOAUTH)
async def delete_star_gift_collection(): return True


# ── Upgrade attributes ────────────────────────────────────────────────────────

@handler.on_request(GetStarGiftUpgradeAttributes, NOAUTH)
async def get_star_gift_upgrade_attributes():
    attrs = await _variant_attrs("variant_file_ids")
    return StarGiftUpgradeAttributes(attributes=attrs)

@handler.on_request(GetUniqueStarGiftValueInfo, NOAUTH)
async def get_unique_star_gift_value_info(): return True


# ── Check / Auction ───────────────────────────────────────────────────────────

@handler.on_request(CheckCanSendGift, NOAUTH)
async def check_can_send_gift():
    return CheckCanSendGiftResultOk()

@handler.on_request(GetStarGiftAuctionState, NOAUTH)
async def get_star_gift_auction_state():
    return StarGiftAuctionState(gift=None, state=None, user_state=None, timeout=0, users=[], chats=[])

@handler.on_request(GetStarGiftAuctionAcquiredGifts, NOAUTH)
async def get_star_gift_auction_acquired_gifts():
    return StarGiftAuctionAcquiredGifts(gifts=[], users=[], chats=[])

@handler.on_request(GetStarGiftActiveAuctions, NOAUTH)
async def get_star_gift_active_auctions():
    return StarGiftActiveAuctionsNotModified()

@handler.on_request(ResolveStarGiftOffer, NOAUTH)
async def resolve_star_gift_offer(): return True

@handler.on_request(SendStarGiftOffer, NOAUTH)
async def send_star_gift_offer(): return True


# ── Stars options ─────────────────────────────────────────────────────────────

@handler.on_request(GetStarsGiftOptions, NOAUTH)
async def get_stars_gift_options():
    return TLObjectVector([
        StarsGiftOption(stars=50,  currency="USD", amount=50),
        StarsGiftOption(stars=100, currency="USD", amount=99),
        StarsGiftOption(stars=500, currency="USD", amount=499),
    ])

@handler.on_request(GetStarsGiveawayOptions, NOAUTH)
async def get_stars_giveaway_options():
    return TLObjectVector([])


# ── StarRef bots ──────────────────────────────────────────────────────────────

@handler.on_request(GetConnectedStarRefBots, NOAUTH)
async def get_connected_star_ref_bots():
    return ConnectedStarRefBots(count=0, connected_bots=[], users=[])

@handler.on_request(GetConnectedStarRefBot, NOAUTH)
async def get_connected_star_ref_bot():
    return ConnectedStarRefBots(count=0, connected_bots=[], users=[])

@handler.on_request(GetSuggestedStarRefBots, NOAUTH)
async def get_suggested_star_ref_bots():
    return SuggestedStarRefBots(count=0, suggested_bots=[], users=[])

@handler.on_request(ConnectStarRefBot, NOAUTH)
async def connect_star_ref_bot():
    return ConnectedStarRefBots(count=0, connected_bots=[], users=[])

@handler.on_request(EditConnectedStarRefBot, NOAUTH)
async def edit_connected_star_ref_bot():
    return ConnectedStarRefBots(count=0, connected_bots=[], users=[])
