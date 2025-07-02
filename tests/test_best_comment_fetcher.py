import pytest
from datetime import date, datetime
from unittest.mock import Mock, patch, MagicMock
import json

from yt_meta.comment_fetcher import BestCommentFetcher
from yt_meta.exceptions import VideoUnavailableError


class TestBestCommentFetcher:
    """
    TDD tests for BestCommentFetcher
    These tests define the expected behavior before implementation
    """
    
    def setup_method(self):
        """Setup for each test"""
        self.fetcher = BestCommentFetcher()
        
    def test_init_creates_proper_client(self):
        """Test that initialization creates proper HTTP client"""
        fetcher = BestCommentFetcher(timeout=30, retries=5)
        assert fetcher.api_client is not None
        assert fetcher.api_client.retries == 5
        assert fetcher.parser is not None
        
    def test_get_comments_validates_since_date_with_sort_by(self):
        """Test that since_date only works with recent sorting"""
        with pytest.raises(ValueError, match="`since_date` can only be used with `sort_by='recent'`"):
            list(self.fetcher.get_comments("test_id", sort_by="top", since_date=date(2023, 1, 1)))
            
    @patch('yt_meta.comment_api_client.httpx.Client')
    def test_get_comments_handles_video_unavailable(self, mock_client_class):
        """Test proper error handling for unavailable videos"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.side_effect = Exception("404 Not Found")
        
        fetcher = BestCommentFetcher()
        
        with pytest.raises(VideoUnavailableError):
            list(fetcher.get_comments("invalid_id"))
            
    def test_comment_data_structure_completeness(self):
        """Test that returned comments have all expected fields with correct types"""
        expected_fields = {
            'id': str,
            'text': str,
            'author': str,
            'author_channel_id': str,
            'author_avatar_url': str,
            'publish_date': (date, type(None)),
            'time_human': str,
            'time_parsed': (float, type(None)),
            'like_count': int,
            'reply_count': int,
            'is_hearted': bool,
            'is_reply': bool,
            'is_pinned': bool,
            'paid_comment': (str, type(None)),
            'author_badges': list,
            'parent_id': (str, type(None)),
        }
        
        # Mock a complete comment response
        with patch.object(self.fetcher.api_client, 'make_api_request') as mock_request, \
             patch.object(self.fetcher.api_client, '_extract_ytcfg') as mock_ytcfg, \
             patch.object(self.fetcher.api_client, '_extract_initial_data') as mock_data, \
             patch.object(self.fetcher.api_client, 'get_sort_endpoints_flexible') as mock_endpoints:
            
            # Setup mocks
            mock_ytcfg.return_value = {"INNERTUBE_API_KEY": "test", "INNERTUBE_CONTEXT": {}}
            mock_data.return_value = {"test": "data"}
            mock_endpoints.return_value = {"top": "test_token"}
            mock_request.return_value = self._create_mock_comment_response()
            
            # Mock the HTTP client
            with patch.object(self.fetcher.api_client.client, 'get') as mock_get:
                mock_response = Mock()
                mock_response.text = self._create_mock_html()
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response
                
                comments = list(self.fetcher.get_comments("test_id", limit=1))
                
                assert len(comments) > 0
                comment = comments[0]
                
                # Check all expected fields exist and have correct types
                for field, expected_type in expected_fields.items():
                    assert field in comment, f"Missing field: {field}"
                    if isinstance(expected_type, tuple):
                        assert isinstance(comment[field], expected_type), f"Field {field} has wrong type: {type(comment[field])}, expected: {expected_type}"
                    else:
                        assert isinstance(comment[field], expected_type), f"Field {field} has wrong type: {type(comment[field])}, expected: {expected_type}"
                        
    def test_engagement_count_parsing(self):
        """Test parsing of engagement counts like '1.2K', '58K', '325K'"""
        fetcher = BestCommentFetcher()
        
        # Test various count formats
        assert fetcher.parser._parse_engagement_count("120") == 120
        assert fetcher.parser._parse_engagement_count("1.2K") == 1200
        assert fetcher.parser._parse_engagement_count("58K") == 58000
        assert fetcher.parser._parse_engagement_count("325K") == 325000
        assert fetcher.parser._parse_engagement_count("1.5M") == 1500000
        assert fetcher.parser._parse_engagement_count("") == 0
        assert fetcher.parser._parse_engagement_count(None) == 0
        assert fetcher.parser._parse_engagement_count("invalid") == 0
        
    def test_flexible_endpoint_detection(self):
        """Test that endpoint detection works with different YouTube structures"""
        fetcher = BestCommentFetcher()
        
        # Test with sortFilterSubMenuRenderer present
        data_with_sort = {
            "nested": {
                "sortFilterSubMenuRenderer": {
                    "subMenuItems": [
                        {
                            "title": "Top comments",
                            "serviceEndpoint": {
                                "continuationCommand": {"token": "top_token"}
                            }
                        },
                        {
                            "title": "Newest first", 
                            "serviceEndpoint": {
                                "continuationCommand": {"token": "recent_token"}
                            }
                        }
                    ]
                }
            }
        }
        
        endpoints = fetcher.api_client.get_sort_endpoints_flexible(data_with_sort, {"INNERTUBE_API_KEY": "test", "INNERTUBE_CONTEXT": {}})
        assert "top comments" in endpoints
        assert "newest first" in endpoints
        assert endpoints["top comments"] == "top_token"
        assert endpoints["newest first"] == "recent_token"
        
    def test_surface_key_mapping(self):
        """Test surface key to comment ID mapping functionality"""
        fetcher = BestCommentFetcher()
        
        data = {
            "commentViewModel": [
                {
                    "commentSurfaceKey": "surface_key_1",
                    "commentId": "comment_id_1"
                },
                {
                    "commentSurfaceKey": "surface_key_2", 
                    "commentId": "comment_id_2"
                }
            ]
        }
        
        surface_keys = fetcher.parser.get_surface_key_mappings(data)
        assert surface_keys["surface_key_1"] == "comment_id_1"
        assert surface_keys["surface_key_2"] == "comment_id_2"
        
    def test_toolbar_states_extraction(self):
        """Test toolbar states extraction for engagement data"""
        fetcher = BestCommentFetcher()
        
        data = {
            "mutations": [
                {
                    "payload": {
                        "engagementToolbarStateEntityPayload": {
                            "key": "toolbar_key_1",
                            "heartState": "TOOLBAR_HEART_STATE_HEARTED"
                        }
                    }
                },
                {
                    "payload": {
                        "engagementToolbarStateEntityPayload": {
                            "key": "toolbar_key_2",
                            "heartState": "TOOLBAR_HEART_STATE_UNHEARTED"
                        }
                    }
                }
            ]
        }
        
        toolbar_states = fetcher.parser.get_toolbar_states(data)
        assert "toolbar_key_1" in toolbar_states
        assert "toolbar_key_2" in toolbar_states
        assert toolbar_states["toolbar_key_1"]["heartState"] == "TOOLBAR_HEART_STATE_HEARTED"
        
    def test_paid_comments_extraction(self):
        """Test paid comment (Super Chat) detection"""
        fetcher = BestCommentFetcher()
        
        surface_keys = {"surface_key_1": "comment_id_1"}
        data = {
            "mutations": [
                {
                    "payload": {
                        "commentSurfaceEntityPayload": {
                            "key": "surface_key_1",
                            "pdgCommentChip": True,
                            "simpleText": "$5.00"
                        }
                    }
                }
            ]
        }
        
        paid_comments = fetcher.parser.get_paid_comments(data, surface_keys)
        assert "comment_id_1" in paid_comments
        assert paid_comments["comment_id_1"] == "$5.00"
        
    def test_progress_callback_called(self):
        """Test that progress callback is called during comment fetching"""
        callback_calls = []
        
        def progress_callback(count):
            callback_calls.append(count)
            
        # Mock the entire flow
        with patch.object(self.fetcher.api_client, 'make_api_request') as mock_request, \
             patch.object(self.fetcher.api_client, '_extract_ytcfg') as mock_ytcfg, \
             patch.object(self.fetcher.api_client, '_extract_initial_data') as mock_data, \
             patch.object(self.fetcher.api_client, 'get_sort_endpoints_flexible') as mock_endpoints:
            
            mock_ytcfg.return_value = {"INNERTUBE_API_KEY": "test", "INNERTUBE_CONTEXT": {}}
            mock_data.return_value = {"test": "data"}
            mock_endpoints.return_value = {"top": "test_token"}
            mock_request.return_value = self._create_mock_comment_response()
            
            with patch.object(self.fetcher.api_client.client, 'get') as mock_get:
                mock_response = Mock()
                mock_response.text = self._create_mock_html()
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response
                
                comments = list(self.fetcher.get_comments("test_id", limit=3, progress_callback=progress_callback))
                
                assert len(callback_calls) > 0
                assert callback_calls == [1, 2, 3]  # Should be called for each comment
                
    def test_limit_respected(self):
        """Test that the limit parameter is properly respected"""
        with patch.object(self.fetcher.api_client, 'make_api_request') as mock_request, \
             patch.object(self.fetcher.api_client, '_extract_ytcfg') as mock_ytcfg, \
             patch.object(self.fetcher.api_client, '_extract_initial_data') as mock_data, \
             patch.object(self.fetcher.api_client, 'get_sort_endpoints_flexible') as mock_endpoints:
            
            mock_ytcfg.return_value = {"INNERTUBE_API_KEY": "test", "INNERTUBE_CONTEXT": {}}
            mock_data.return_value = {"test": "data"}
            mock_endpoints.return_value = {"top": "test_token"}
            
            # Create response with multiple comments
            mock_request.return_value = self._create_mock_comment_response(num_comments=10)
            
            with patch.object(self.fetcher.api_client.client, 'get') as mock_get:
                mock_response = Mock()
                mock_response.text = self._create_mock_html()
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response
                
                comments = list(self.fetcher.get_comments("test_id", limit=3))
                
                assert len(comments) == 3
                
    def test_since_date_filtering(self):
        """Test that since_date filtering works correctly"""
        cutoff_date = date(2023, 1, 1)
        
        with patch.object(self.fetcher.api_client, 'make_api_request') as mock_request, \
             patch.object(self.fetcher.api_client, '_extract_ytcfg') as mock_ytcfg, \
             patch.object(self.fetcher.api_client, '_extract_initial_data') as mock_data, \
             patch.object(self.fetcher.api_client, 'get_sort_endpoints_flexible') as mock_endpoints:
            
            mock_ytcfg.return_value = {"INNERTUBE_API_KEY": "test", "INNERTUBE_CONTEXT": {}}
            mock_data.return_value = {"test": "data"}
            mock_endpoints.return_value = {"recent": "test_token"}
            
            # Create response with comments before and after cutoff
            mock_request.return_value = self._create_mock_comment_response_with_dates()
            
            with patch.object(self.fetcher.api_client.client, 'get') as mock_get:
                mock_response = Mock()
                mock_response.text = self._create_mock_html()
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response
                
                comments = list(self.fetcher.get_comments("test_id", sort_by="recent", since_date=cutoff_date))
                
                # All returned comments should be after the cutoff date
                for comment in comments:
                    if comment['publish_date']:
                        assert comment['publish_date'] >= cutoff_date
                        
    def _create_mock_html(self):
        """Create mock HTML with required ytcfg and initial data"""
        return """
        <script>
        ytcfg.set({"INNERTUBE_API_KEY": "test_key", "INNERTUBE_CONTEXT": {"client": {"clientName": "WEB"}}});
        </script>
        <script>
        var ytInitialData = {"contents": {"test": "data"}};
        </script>
        """
        
    def _create_mock_comment_response(self, num_comments=3):
        """Create mock API response with comment data"""
        mutations = []
        
        # Create comment entity payloads
        for i in range(num_comments):
            mutations.append({
                "payload": {
                    "commentEntityPayload": {
                        "properties": {
                            "commentId": f"comment_id_{i}",
                            "content": {"content": f"Test comment {i}"},
                            "publishedTime": "2 years ago",
                            "toolbarStateKey": f"toolbar_key_{i}",
                            "authorKey": f"author_key_{i}"
                        }
                    }
                }
            })
            
        # Create author entity payloads
        for i in range(num_comments):
            mutations.append({
                "payload": {
                    "authorEntityPayload": {
                        "key": f"author_key_{i}",
                        "displayName": f"TestUser{i}",
                        "channelId": f"UC_channel_{i}",
                        "avatarThumbnailUrl": f"https://avatar{i}.jpg"
                    }
                }
            })
            
        # Create toolbar entity payloads
        for i in range(num_comments):
            mutations.append({
                "payload": {
                    "engagementToolbarEntityPayload": {
                        "key": f"toolbar_key_{i}",
                        "likeCountNotliked": str(100 + i),
                        "replyCount": str(i)
                    }
                }
            })
            
        return {
            "frameworkUpdates": {
                "entityBatchUpdate": {
                    "mutations": mutations
                }
            },
            "commentViewModel": [
                {"commentSurfaceKey": f"surface_key_{i}", "commentId": f"comment_id_{i}"}
                for i in range(num_comments)
            ]
        }
        
    def _create_mock_comment_response_with_dates(self):
        """Create mock response with comments having different dates for filtering tests"""
        mutations = [
            # New comment
            {
                "payload": {
                    "commentEntityPayload": {
                        "properties": {
                            "commentId": "new_comment",
                            "content": {"content": "New comment"},
                            "publishedTime": "1 month ago",
                            "toolbarStateKey": "toolbar_key_new",
                            "authorKey": "author_key_new"
                        }
                    }
                }
            },
            {
                "payload": {
                    "authorEntityPayload": {
                        "key": "author_key_new",
                        "displayName": "NewUser",
                        "channelId": "UC_new",
                        "avatarThumbnailUrl": "https://avatar_new.jpg"
                    }
                }
            },
            {
                "payload": {
                    "engagementToolbarEntityPayload": {
                        "key": "toolbar_key_new",
                        "likeCountNotliked": "100",
                        "replyCount": "5"
                    }
                }
            },
            # Old comment
            {
                "payload": {
                    "commentEntityPayload": {
                        "properties": {
                            "commentId": "old_comment",
                            "content": {"content": "Old comment"},
                            "publishedTime": "3 years ago",
                            "toolbarStateKey": "toolbar_key_old",
                            "authorKey": "author_key_old"
                        }
                    }
                }
            },
            {
                "payload": {
                    "authorEntityPayload": {
                        "key": "author_key_old",
                        "displayName": "OldUser",
                        "channelId": "UC_old",
                        "avatarThumbnailUrl": "https://avatar_old.jpg"
                    }
                }
            },
            {
                "payload": {
                    "engagementToolbarEntityPayload": {
                        "key": "toolbar_key_old",
                        "likeCountNotliked": "50",
                        "replyCount": "2"
                    }
                }
            }
        ]
        
        return {
            "frameworkUpdates": {
                "entityBatchUpdate": {
                    "mutations": mutations
                }
            },
            "commentViewModel": [
                {"commentSurfaceKey": "surface_key_new", "commentId": "new_comment"},
                {"commentSurfaceKey": "surface_key_old", "commentId": "old_comment"}
            ]
        } 