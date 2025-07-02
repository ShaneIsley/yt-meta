#!/usr/bin/env python3
"""
Performance Benchmark: BestCommentFetcher vs YouTube Comment Downloader
"""

import time
import logging
import traceback
from datetime import datetime
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

# Our implementation
from yt_meta.best_comment_fetcher import BestCommentFetcher

# YouTube Comment Downloader
try:
    from youtube_comment_downloader import YoutubeCommentDownloader
    YCD_AVAILABLE = True
except ImportError:
    YCD_AVAILABLE = False
    print("❌ youtube-comment-downloader not available")


@dataclass
class BenchmarkResult:
    """Results from a single benchmark test."""
    fetcher_name: str
    video_url: str
    limit: int
    sort_by: str
    comments_fetched: int
    time_taken: float
    comments_per_sec: float
    success: bool
    error: str = ""
    sample_comment: Dict[str, Any] = None


class CommentFetcherBenchmark:
    """Comprehensive benchmark for comment fetchers."""
    
    def __init__(self):
        self.setup_logging()
        self.results: List[BenchmarkResult] = []
        
    def setup_logging(self):
        """Setup logging to suppress verbose output during benchmarking."""
        logging.getLogger('yt_meta.best_comment_fetcher').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        
    def benchmark_best_comment_fetcher(
        self, 
        video_url: str, 
        limit: int = 50, 
        sort_by: str = "top"
    ) -> BenchmarkResult:
        """Benchmark our BestCommentFetcher implementation."""
        
        print(f"🚀 Testing BestCommentFetcher...")
        
        try:
            fetcher = BestCommentFetcher()
            start_time = time.time()
            
            comments = []
            for comment in fetcher.get_comments(video_url, limit=limit, sort_by=sort_by):
                comments.append(comment)
                
            end_time = time.time()
            time_taken = end_time - start_time
            comments_per_sec = len(comments) / time_taken if time_taken > 0 else 0
            
            sample_comment = comments[0] if comments else None
            
            return BenchmarkResult(
                fetcher_name="BestCommentFetcher",
                video_url=video_url,
                limit=limit,
                sort_by=sort_by,
                comments_fetched=len(comments),
                time_taken=time_taken,
                comments_per_sec=comments_per_sec,
                success=True,
                sample_comment=sample_comment
            )
            
        except Exception as e:
            return BenchmarkResult(
                fetcher_name="BestCommentFetcher",
                video_url=video_url,
                limit=limit,
                sort_by=sort_by,
                comments_fetched=0,
                time_taken=0,
                comments_per_sec=0,
                success=False,
                error=str(e)
            )
    
    def benchmark_ycd(
        self, 
        video_url: str, 
        limit: int = 50, 
        sort_by: str = "top"
    ) -> BenchmarkResult:
        """Benchmark YouTube Comment Downloader implementation."""
        
        if not YCD_AVAILABLE:
            return BenchmarkResult(
                fetcher_name="YCD",
                video_url=video_url,
                limit=limit,
                sort_by=sort_by,
                comments_fetched=0,
                time_taken=0,
                comments_per_sec=0,
                success=False,
                error="YCD not available"
            )
        
        print(f"📥 Testing YouTube Comment Downloader...")
        
        try:
            # Extract video ID
            video_id = video_url.split('v=')[1].split('&')[0] if 'v=' in video_url else video_url
            
            downloader = YoutubeCommentDownloader()
            start_time = time.time()
            
            # YCD has API issues with get_comments_from_url, use get_comments with video ID
            comments = []
            for comment in downloader.get_comments(video_id):
                comments.append(comment)
                if len(comments) >= limit:
                    break
                    
            end_time = time.time()
            time_taken = end_time - start_time
            comments_per_sec = len(comments) / time_taken if time_taken > 0 else 0
            
            sample_comment = comments[0] if comments else None
            
            return BenchmarkResult(
                fetcher_name="YCD",
                video_url=video_url,
                limit=limit,
                sort_by=sort_by,
                comments_fetched=len(comments),
                time_taken=time_taken,
                comments_per_sec=comments_per_sec,
                success=True,
                sample_comment=sample_comment
            )
            
        except Exception as e:
            return BenchmarkResult(
                fetcher_name="YCD",
                video_url=video_url,
                limit=limit,
                sort_by=sort_by,
                comments_fetched=0,
                time_taken=0,
                comments_per_sec=0,
                success=False,
                error=str(e)
            )
    
    def run_comparison(
        self, 
        video_url: str, 
        limit: int = 50, 
        sort_by: str = "top"
    ) -> Tuple[BenchmarkResult, BenchmarkResult]:
        """Run comparison between both fetchers."""
        
        print(f"\n{'='*80}")
        print(f"🏁 BENCHMARK: {video_url}")
        print(f"📊 Limit: {limit} comments | Sort: {sort_by}")
        print(f"{'='*80}")
        
        # Test our implementation
        best_result = self.benchmark_best_comment_fetcher(video_url, limit, sort_by)
        self.results.append(best_result)
        
        # Test YCD
        ycd_result = self.benchmark_ycd(video_url, limit, sort_by)
        self.results.append(ycd_result)
        
        # Display results
        self.display_comparison(best_result, ycd_result)
        
        return best_result, ycd_result
    
    def display_comparison(self, best_result: BenchmarkResult, ycd_result: BenchmarkResult):
        """Display comparison results."""
        
        print(f"\n📊 PERFORMANCE RESULTS:")
        print(f"{'─'*60}")
        
        # Performance comparison table
        print(f"{'Fetcher':<20} {'Success':<8} {'Comments':<10} {'Time (s)':<10} {'Rate (c/s)':<12}")
        print(f"{'─'*60}")
        
        success_icon = "✅" if best_result.success else "❌"
        print(f"{'BestCommentFetcher':<20} {success_icon:<8} {best_result.comments_fetched:<10} "
              f"{best_result.time_taken:<10.2f} {best_result.comments_per_sec:<12.1f}")
        
        success_icon = "✅" if ycd_result.success else "❌"
        print(f"{'YCD':<20} {success_icon:<8} {ycd_result.comments_fetched:<10} "
              f"{ycd_result.time_taken:<10.2f} {ycd_result.comments_per_sec:<12.1f}")
        
        # Performance winner
        if best_result.success and ycd_result.success:
            if best_result.comments_per_sec > ycd_result.comments_per_sec:
                improvement = ((best_result.comments_per_sec - ycd_result.comments_per_sec) / 
                              ycd_result.comments_per_sec * 100)
                print(f"\n🏆 BestCommentFetcher is {improvement:.1f}% faster!")
            elif ycd_result.comments_per_sec > best_result.comments_per_sec:
                improvement = ((ycd_result.comments_per_sec - best_result.comments_per_sec) / 
                              best_result.comments_per_sec * 100)
                print(f"\n🏆 YCD is {improvement:.1f}% faster!")
            else:
                print(f"\n🤝 Performance is roughly equal!")
        
        # Data quality comparison
        print(f"\n📄 DATA QUALITY COMPARISON:")
        print(f"{'─'*40}")
        
        if best_result.sample_comment and ycd_result.sample_comment:
            self.compare_data_quality(best_result.sample_comment, ycd_result.sample_comment)
        
        # Error reporting
        if not best_result.success:
            print(f"\n❌ BestCommentFetcher Error: {best_result.error}")
        if not ycd_result.success:
            print(f"\n❌ YCD Error: {ycd_result.error}")
    
    def compare_data_quality(self, best_comment: Dict, ycd_comment: Dict):
        """Compare data quality between fetchers."""
        
        # Map YCD fields to our fields for comparison
        comparisons = [
            ("Author", best_comment.get('author', 'N/A'), ycd_comment.get('author', 'N/A')),
            ("Likes", best_comment.get('like_count', 0), ycd_comment.get('votes', 0)),
            ("Text Length", len(best_comment.get('text', '')), len(ycd_comment.get('text', ''))),
            ("Time", best_comment.get('time_human', 'N/A'), ycd_comment.get('time', 'N/A')),
            ("Channel ID", "✅" if best_comment.get('author_channel_id') else "❌", 
             "✅" if ycd_comment.get('channel') else "❌"),
            ("Avatar URL", "✅" if best_comment.get('author_avatar_url') else "❌",
             "✅" if ycd_comment.get('photo') else "❌"),
        ]
        
        for field, best_val, ycd_val in comparisons:
            print(f"{field:<12} | Best: {str(best_val):<25} | YCD: {str(ycd_val):<25}")
    
    def run_comprehensive_benchmark(self):
        """Run comprehensive benchmark across multiple scenarios."""
        
        print("🎯 COMPREHENSIVE COMMENT FETCHER BENCHMARK")
        print("=" * 80)
        print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Test scenarios: (video_url, limit, sort_by, description)
        test_scenarios = [
            # Different video types and sizes
            ("https://www.youtube.com/watch?v=B68agR-OeJM", 20, "top", "Music Video - Medium Comments"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", 30, "top", "Viral Video - Many Comments"),
            ("https://www.youtube.com/watch?v=B68agR-OeJM", 15, "recent", "Music Video - Recent Comments"),
            
            # Different limits to test scalability
            ("https://www.youtube.com/watch?v=B68agR-OeJM", 5, "top", "Small Batch Test"),
            ("https://www.youtube.com/watch?v=B68agR-OeJM", 50, "top", "Large Batch Test"),
        ]
        
        all_best_results = []
        all_ycd_results = []
        
        for video_url, limit, sort_by, description in test_scenarios:
            print(f"\n🧪 {description}")
            try:
                best_result, ycd_result = self.run_comparison(video_url, limit, sort_by)
                all_best_results.append(best_result)
                all_ycd_results.append(ycd_result)
            except Exception as e:
                print(f"❌ Test failed: {e}")
                traceback.print_exc()
        
        # Overall summary
        self.display_overall_summary(all_best_results, all_ycd_results)
    
    def display_overall_summary(self, best_results: List[BenchmarkResult], ycd_results: List[BenchmarkResult]):
        """Display overall benchmark summary."""
        
        print(f"\n{'='*80}")
        print("📊 OVERALL BENCHMARK SUMMARY")
        print(f"{'='*80}")
        
        # Calculate averages for successful tests
        successful_best = [r for r in best_results if r.success]
        successful_ycd = [r for r in ycd_results if r.success]
        
        if successful_best:
            avg_best_rate = sum(r.comments_per_sec for r in successful_best) / len(successful_best)
            avg_best_time = sum(r.time_taken for r in successful_best) / len(successful_best)
            total_best_comments = sum(r.comments_fetched for r in successful_best)
        else:
            avg_best_rate = 0
            avg_best_time = 0
            total_best_comments = 0
            
        if successful_ycd:
            avg_ycd_rate = sum(r.comments_per_sec for r in successful_ycd) / len(successful_ycd)
            avg_ycd_time = sum(r.time_taken for r in successful_ycd) / len(successful_ycd)
            total_ycd_comments = sum(r.comments_fetched for r in successful_ycd)
        else:
            avg_ycd_rate = 0
            avg_ycd_time = 0
            total_ycd_comments = 0
        
        print(f"\n📈 PERFORMANCE SUMMARY:")
        print(f"{'─'*70}")
        print(f"{'Fetcher':<20} {'Success Rate':<12} {'Avg Rate (c/s)':<15} {'Avg Time (s)':<12} {'Total Comments':<15}")
        print(f"{'─'*70}")
        
        best_success_rate = len(successful_best) / len(best_results) * 100 if best_results else 0
        ycd_success_rate = len(successful_ycd) / len(ycd_results) * 100 if ycd_results else 0
        
        print(f"{'BestCommentFetcher':<20} {best_success_rate:<12.1f}% {avg_best_rate:<15.1f} "
              f"{avg_best_time:<12.2f} {total_best_comments:<15}")
        print(f"{'YCD':<20} {ycd_success_rate:<12.1f}% {avg_ycd_rate:<15.1f} "
              f"{avg_ycd_time:<12.2f} {total_ycd_comments:<15}")
        
        # Overall winner
        print(f"\n🏆 OVERALL WINNER:")
        if avg_best_rate > avg_ycd_rate and best_success_rate >= ycd_success_rate:
            improvement = ((avg_best_rate - avg_ycd_rate) / avg_ycd_rate * 100) if avg_ycd_rate > 0 else float('inf')
            print(f"   🥇 BestCommentFetcher wins with {improvement:.1f}% better performance!")
        elif avg_ycd_rate > avg_best_rate and ycd_success_rate >= best_success_rate:
            improvement = ((avg_ycd_rate - avg_best_rate) / avg_best_rate * 100) if avg_best_rate > 0 else float('inf')
            print(f"   🥇 YCD wins with {improvement:.1f}% better performance!")
        else:
            print(f"   🤝 Performance is competitive between both implementations")
        
        # Recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        if best_success_rate > ycd_success_rate:
            print(f"   ✅ BestCommentFetcher has better reliability ({best_success_rate:.1f}% vs {ycd_success_rate:.1f}%)")
        if avg_best_rate > avg_ycd_rate:
            print(f"   ⚡ BestCommentFetcher has better throughput ({avg_best_rate:.1f} vs {avg_ycd_rate:.1f} c/s)")
        
        print(f"\n🕐 Benchmark completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def main():
    """Run the benchmark."""
    
    if not YCD_AVAILABLE:
        print("❌ youtube-comment-downloader is not installed!")
        print("📦 Install with: uv add youtube-comment-downloader")
        return
    
    benchmark = CommentFetcherBenchmark()
    
    try:
        benchmark.run_comprehensive_benchmark()
    except KeyboardInterrupt:
        print("\n⏹️ Benchmark interrupted by user")
    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main() 