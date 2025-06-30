"""
Centralized constants for URLs, regex patterns, and API dictionary keys.
"""

# --- URLs and Regex ---
YOUTUBE_VIDEO_URL = "https://www.youtube.com/watch?v={youtube_id}"
YOUTUBE_API_URL = "https://www.youtube.com/youtubei/v1/next"
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'

YT_CFG_RE = r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;'
YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;\s*(?:var\s+meta|</script|\n)'

# --- YouTube API Keys ---

# Root keys
KEY_ENGAGEMENT_PANELS = "engagementPanels"
KEY_FRAMEWORK_UPDATES = "frameworkUpdates"
KEY_ON_RESPONSE_RECEIVED_ENDPOINTS = "onResponseReceivedEndpoints"

# Command and Continuation keys
KEY_CONTINUATION = "continuation"
KEY_CONTINUATION_COMMAND = "continuationCommand"
KEY_CONTINUATION_ENDPOINT = "continuationEndpoint"
KEY_CONTINUATION_ITEM_RENDERER = "continuationItemRenderer"
KEY_CONTINUATION_ITEMS = "continuationItems"
KEY_APPEND_CONTINUATION_ITEMS_ACTION = "appendContinuationItemsAction"
KEY_RELOAD_CONTINUATION_ITEMS_COMMAND = "reloadContinuationItemsCommand"
KEY_SERVICE_ENDPOINT = "serviceEndpoint"
KEY_SUB_MENU_ITEMS = "subMenuItems"
KEY_SORT_FILTER_SUB_MENU_RENDERER = "sortFilterSubMenuRenderer"
KEY_TOKEN = "token"

# Comment structure keys
KEY_COMMENT_ENTITY_PAYLOAD = "commentEntityPayload"
KEY_COMMENT_REPLIES_RENDERER = "commentRepliesRenderer"
KEY_COMMENT_THREAD_RENDERER = "commentThreadRenderer"
KEY_PROPERTIES = "properties"
KEY_TOOLBAR = "toolbar"
KEY_REPLIES = "replies"

# Comment author and metadata keys
KEY_AUTHOR = "author"
KEY_AUTHOR_BADGES = "authorBadges"
KEY_AVATAR_THUMBNAIL_URL = "avatarThumbnailUrl"
KEY_BADGE_RENDERER = "badgeRenderer"
KEY_BROWSE_ENDPOINT = "browseEndpoint"
KEY_CHANNEL_ID = "channelId"
KEY_CHANNEL_RENDERER = "channelRenderer"
KEY_DISPLAY_NAME = "displayName"
KEY_ICON = "icon"
KEY_ICON_TYPE = "iconType"
KEY_IS_CREATOR = "isCreator"
KEY_IS_PINNED = "isPinned"
KEY_IS_VERIFIED = "isVerified"
KEY_METADATA_BADGE_RENDERER = "metadataBadgeRenderer"
KEY_NAVIGATION_ENDPOINT = "navigationEndpoint"
KEY_OWNER_BADGES = "ownerBadges"
KEY_REPLY_COUNT = "replyCount"

# Content and text keys
KEY_CONTENT = "content"
KEY_CONTENT_TEXT = "contentText" # Legacy key for some comments
KEY_PUBLISHED_TIME = "publishedTime"
KEY_RUNS = "runs"
KEY_TEXT = "text"
KEY_TITLE = "title"

# Context and config keys
KEY_CONTEXT = "context"
KEY_INNERTUBE_API_KEY = "INNERTUBE_API_KEY"
KEY_INNERTUBE_CONTEXT = "INNERTUBE_CONTEXT"

# Miscellaneous
KEY_MUTATIONS = "mutations"
KEY_PAYLOAD = "payload"
KEY_ENTITY_BATCH_UPDATE = "entityBatchUpdate"
KEY_ENGAGEMENT_PANEL_SECTION_LIST_RENDERER = "engagementPanelSectionListRenderer"
KEY_HEADER = "header"
KEY_ENGAGEMENT_PANEL_TITLE_HEADER_RENDERER = "engagementPanelTitleHeaderRenderer"
KEY_CONTENTS = "contents"
KEY_MENU = "menu" 