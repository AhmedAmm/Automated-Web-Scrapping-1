import google.generativeai as genai
import os
import time
import random
import threading
import array
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from collections import deque
from dotenv import load_dotenv

load_dotenv()

class RateLimiter:
    """Multi-tier rate limiting with microsecond precision using token bucket algorithm"""
    def __init__(self, rate: int, per: int, burst: int = 3):
        self.rate = rate  # 15 queries per minute
        self.per = per    # 60 seconds
        self.burst = burst  # 3 queries per second burst
        self.tokens = rate
        self.burst_tokens = burst
        self.last_check = time.time()
        self.last_burst_check = time.time()
        self.lock = threading.Lock()
    
    def consume(self) -> bool:
        """Consume one token if available"""
        with self.lock:
            now = time.time()
            
            # Refill tokens based on elapsed time
            elapsed = now - self.last_check
            self.tokens = min(self.rate, self.tokens + elapsed * (self.rate / self.per))
            self.last_check = now
            
            # Refill burst tokens
            burst_elapsed = now - self.last_burst_check
            self.burst_tokens = min(self.burst, self.burst_tokens + burst_elapsed * self.burst)
            self.last_burst_check = now
            
            # Check if we have tokens available
            if self.tokens >= 1 and self.burst_tokens >= 1:
                self.tokens -= 1
                self.burst_tokens -= 1
                return True
            return False
    
    def get_tokens(self) -> Tuple[float, float]:
        """Get current token counts for monitoring"""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_check
            tokens = min(self.rate, self.tokens + elapsed * (self.rate / self.per))
            
            burst_elapsed = now - self.last_burst_check
            burst_tokens = min(self.burst, self.burst_tokens + burst_elapsed * self.burst)
            
            return tokens, burst_tokens

class DailyQuotaManager:
    """Track 1000 queries/day per key with UTC reset"""
    def __init__(self, daily_limit: int = 1000, key_count: int = 6):
        self.daily_limit = daily_limit
        self.key_count = key_count
        # Use array for memory efficiency (24 bytes vs 200+ bytes for dict)
        self.usage = array.array('I', [0] * key_count)
        self.last_reset = self._get_next_reset_time()
        self.lock = threading.Lock()
    
    def _get_next_reset_time(self) -> float:
        """Get next UTC midnight timestamp"""
        now = datetime.now(timezone.utc)
        reset_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if reset_time <= now:
            reset_time = reset_time.replace(day=now.day + 1)
        return reset_time.timestamp()
    
    def consume(self, key_index: int) -> bool:
        """Consume one quota for the specified key"""
        with self.lock:
            # Check if we need to reset (UTC midnight)
            now = time.time()
            if now >= self.last_reset:
                self.usage = array.array('I', [0] * self.key_count)
                self.last_reset = self._get_next_reset_time()
            
            # Check and consume quota
            if self.usage[key_index] < self.daily_limit:
                self.usage[key_index] += 1
                return True
            return False
    
    def get_remaining(self, key_index: int) -> int:
        """Get remaining quota for the specified key"""
        with self.lock:
            now = time.time()
            if now >= self.last_reset:
                return self.daily_limit
            return self.daily_limit - self.usage[key_index]
    
    def get_time_until_reset(self) -> float:
        """Get seconds until next quota reset"""
        with self.lock:
            now = time.time()
            if now >= self.last_reset:
                return 0.0
            return self.last_reset - now

class BurstController:
    """Handle 3 queries/second bursts with token bucket"""
    def __init__(self, burst_limit: int = 3):
        self.burst_limit = burst_limit
        self.burst_tokens = burst_limit
        self.last_burst_check = time.time()
        self.lock = threading.Lock()
    
    def consume(self) -> bool:
        """Consume one burst token if available"""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_burst_check
            
            # Refill tokens based on elapsed time
            self.burst_tokens = min(
                self.burst_limit, 
                self.burst_tokens + elapsed * self.burst_limit
            )
            self.last_burst_check = now
            
            # Check if we have tokens available
            if self.burst_tokens >= 1:
                self.burst_tokens -= 1
                return True
            return False
    
    def get_tokens(self) -> float:
        """Get current burst token count"""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_burst_check
            return min(self.burst_limit, self.burst_tokens + elapsed * self.burst_limit)

class MetricsCollector:
    """Collect performance metrics for monitoring"""
    def __init__(self, key_count: int = 6):
        self.key_count = key_count
        # Fixed-size arrays for memory efficiency
        self.queries_per_minute = array.array('I', [0] * key_count)
        self.queries_per_day = array.array('I', [0] * key_count)
        self.failures = array.array('I', [0] * key_count)
        self.response_times = [deque(maxlen=100) for _ in range(key_count)]
        self.last_minute_reset = time.time()
        self.lock = threading.Lock()
    
    def record_query(self, key_index: int, response_time: float):
        """Record a successful query"""
        with self.lock:
            now = time.time()
            
            # Reset minute counters if needed
            if now - self.last_minute_reset >= 60:
                self.queries_per_minute = array.array('I', [0] * self.key_count)
                self.last_minute_reset = now
            
            self.queries_per_minute[key_index] += 1
            self.queries_per_day[key_index] += 1
            self.response_times[key_index].append(response_time)
    
    def record_failure(self, key_index: int):
        """Record a failed query"""
        with self.lock:
            self.failures[key_index] += 1
    
    def get_metrics(self, key_index: int) -> Dict:
        """Get metrics for a specific key"""
        with self.lock:
            response_times = list(self.response_times[key_index])
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            return {
                'queries_per_minute': self.queries_per_minute[key_index],
                'queries_per_day': self.queries_per_day[key_index],
                'failures': self.failures[key_index],
                'avg_response_time': avg_response_time,
                'success_rate': (
                    (self.queries_per_day[key_index] - self.failures[key_index]) / 
                    max(1, self.queries_per_day[key_index])
                ) * 100
            }

class EnhancedRotatingGeminiClient:
    """Production-grade Gemini client with advanced rate limiting and load balancing"""
    
    def __init__(self, base_cooldown=60, max_retries=3, exponential_backoff=True):
        # Load API keys
        self.api_keys = []
        for i in range(1, 7): 
            key = os.getenv(f'api_key{i}')
            if key:
                self.api_keys.append(key)
            else:
                print(f"Warning: api_key{i} not found in .env file")
        
        if not self.api_keys:
            raise ValueError("No API keys found in .env file")
        
        print(f"Loaded {len(self.api_keys)} API keys")
        
        # Initialize rate limiting components
        self.key_count = len(self.api_keys)
        self.rate_limiters = [RateLimiter(15, 60, 3) for _ in range(self.key_count)]
        self.daily_quota = DailyQuotaManager(1000, self.key_count)
        self.burst_controllers = [BurstController(3) for _ in range(self.key_count)]
        
        # Metrics collection
        self.metrics = MetricsCollector(self.key_count)
        
        # Rate limiting and retry configuration
        self.base_cooldown = base_cooldown
        self.max_retries = max_retries
        self.exponential_backoff = exponential_backoff
        
        # Track rate limited keys and when they can be used again
        self.rate_limited_keys = {}  # {key_index: timestamp_when_available}
        self.key_lock = threading.Lock()
        
        self.current_key_index = 0
        self._configure_current_key()
    
    def _configure_current_key(self):
        """Configure the current API key"""
        current_key = self.api_keys[self.current_key_index]
        genai.configure(api_key=current_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash-lite')
    
    def _get_optimal_key(self) -> int:
        """
        Select key based on:
        1. Daily quota availability
        2. Current minute usage
        3. Burst capacity
        
        Returns: key_index (0-5)
        """
        with self.key_lock:
            # Calculate weights for each key
            weights = []
            
            for i in range(self.key_count):
                # Skip rate-limited keys
                if i in self.rate_limited_keys and time.time() < self.rate_limited_keys[i]:
                    weights.append(-1)  # Mark as unavailable
                    continue
                
                # Get daily quota remaining
                daily_remaining = self.daily_quota.get_remaining(i)
                daily_ratio = daily_remaining / 1000.0  # Normalize to 0-1
                
                # Get rate limiter tokens
                rate_tokens, burst_tokens = self.rate_limiters[i].get_tokens()
                
                # Calculate weight
                weight = daily_ratio * (rate_tokens / 15.0) * (burst_tokens / 3.0)
                weights.append(weight)
            
            # Find key with highest weight
            max_weight = max(weights)
            if max_weight <= 0:
                # All keys are rate limited or exhausted
                return None
            
            # Return first key with max weight
            return weights.index(max_weight)
    
    def _check_rate_limits(self, key_index: int) -> bool:
        """
        Check all three tiers:
        - Daily quota: < 1000/day
        - Minute rate: < 15/min
        - Burst rate: < 3/second
        
        Returns: bool (can use this key?)
        """
        # Check daily quota
        if not self.daily_quota.consume(key_index):
            return False
        
        # Check minute rate and burst
        if not self.rate_limiters[key_index].consume():
            return False
        
        # Check burst controller
        if not self.burst_controllers[key_index].consume():
            return False
        
        return True
    
    def _mark_key_rate_limited(self, key_index: int, retry_attempt: int = 0):
        """Mark a key as rate limited with cooldown period"""
        current_time = time.time()
        
        if self.exponential_backoff:
            # Exponential backoff: base_cooldown * (2 ^ retry_attempt) + random jitter
            cooldown = self.base_cooldown * (2 ** retry_attempt)
            jitter = random.uniform(0, min(cooldown * 0.1, 10))  # Up to 10% jitter, max 10 seconds
            cooldown += jitter
        else:
            # Linear backoff with jitter
            cooldown = self.base_cooldown + (retry_attempt * 30) + random.uniform(0, 10)
        
        available_at = current_time + cooldown
        self.rate_limited_keys[key_index] = available_at
        
        print(f"API key {key_index + 1} rate limit exceeded. Available again in {cooldown:.1f} seconds")
    
    def _is_rate_limit_error(self, error):
        """Check if the error is related to rate limiting"""
        error_str = str(error).lower()
        rate_limit_indicators = [
            'rate limit',
            'quota exceeded',
            'too many requests',
            'resource_exhausted',
            '429',
            'rate_limit_exceeded'
        ]
        return any(indicator in error_str for indicator in rate_limit_indicators)
    
    def _get_clean_error_message(self, error):
        """Return a clean, simplified error message"""
        error_str = str(error)
        
        # Check for rate limit errors
        if self._is_rate_limit_error(error):
            return "Rate limit exceeded"
        
        # Check for other common errors
        if "400" in error_str or "invalid" in error_str.lower():
            return "Invalid request"
        elif "401" in error_str or "unauthorized" in error_str.lower():
            return "Authentication failed"
        elif "403" in error_str or "forbidden" in error_str.lower():
            return "Access forbidden"
        elif "500" in error_str or "internal" in error_str.lower():
            return "Server error"
        elif "timeout" in error_str.lower():
            return "Request timeout"
        elif "network" in error_str.lower() or "connection" in error_str.lower():
            return "Network error"
        else:
            # For any other error, return a generic message
            return "API error occurred"
    
    def ask_gemini(self, prompt, thread_id=None):
        """Send a prompt to Gemini with advanced rate limiting and load balancing"""
        thread_prefix = f"[Thread {thread_id}] " if thread_id else ""
        
        retry_attempt = 0
        
        while True:  # Infinite loop until successful response
            start_time = time.time()
            
            try:
                # Find optimal key
                key_index = self._get_optimal_key()
                if key_index is None:
                    # All keys are rate limited, wait for the next available
                    next_available = min(self.rate_limited_keys.values()) if self.rate_limited_keys else time.time() + 60
                    wait_time = max(0, next_available - time.time())
                    print(f"{thread_prefix}All API keys rate limited. Waiting {wait_time:.1f} seconds...")
                    time.sleep(wait_time)
                    continue
                
                # Check rate limits
                if not self._check_rate_limits(key_index):
                    # Rate limit exceeded, mark as limited and try next key
                    self._mark_key_rate_limited(key_index, retry_attempt)
                    continue
                
                # Configure the selected key
                self.current_key_index = key_index
                self._configure_current_key()
                
                print(f"{thread_prefix}Attempting request using API key {key_index + 1}")
                
                # Make the request
                response = self.model.generate_content(prompt)
                
                # Check if response has valid content
                if response and hasattr(response, 'text') and response.text:
                    result = response.text.strip()
                    if result:  # Only return if we have actual content
                        response_time = time.time() - start_time
                        self.metrics.record_query(key_index, response_time)
                        
                        print(f"{thread_prefix}Success with API key {key_index + 1} in {response_time:.2f}s")
                        return result
                    else:
                        print(f"{thread_prefix}Empty response received, retrying...")
                        time.sleep(random.uniform(1, 3))
                        continue
                else:
                    print(f"{thread_prefix}Invalid response received, retrying...")
                    time.sleep(random.uniform(1, 3))
                    continue
                
            except Exception as e:
                response_time = time.time() - start_time
                clean_error = self._get_clean_error_message(e)
                print(f"{thread_prefix}Error with API key {self.current_key_index + 1}: {clean_error} - Retrying...")
                
                # Record failure
                if hasattr(self, 'current_key_index'):
                    self.metrics.record_failure(self.current_key_index)
                
                # Check if it's a rate limit error
                if self._is_rate_limit_error(e) and hasattr(self, 'current_key_index'):
                    self._mark_key_rate_limited(self.current_key_index, retry_attempt)
                
                # Increment retry attempt
                retry_attempt += 1
                
                # Add a small delay before retry
                time.sleep(random.uniform(1, 3))
                continue  # Go back to beginning of while loop
    
    def get_status(self):
        """Get current status of all API keys"""
        current_time = time.time()
        
        status = {
            'total_keys': self.key_count,
            'current_key': self.current_key_index + 1,
            'rate_limited_keys': len(self.rate_limited_keys),
            'available_keys': self.key_count - len(self.rate_limited_keys),
            'time_until_quota_reset': self.daily_quota.get_time_until_reset(),
            'keys': []
        }
        
        for i in range(self.key_count):
            key_status = {
                'key_index': i + 1,
                'daily_quota_remaining': self.daily_quota.get_remaining(i),
                'rate_limited': i in self.rate_limited_keys,
                'time_until_available': (
                    max(0, self.rate_limited_keys[i] - current_time) 
                    if i in self.rate_limited_keys else 0
                ),
                'metrics': self.metrics.get_metrics(i)
            }
            
            # Add rate limiter status
            tokens, burst_tokens = self.rate_limiters[i].get_tokens()
            key_status['rate_limit_tokens'] = tokens
            key_status['burst_tokens'] = burst_tokens
            
            status['keys'].append(key_status)
        
        return status
    
    def get_system_health(self) -> Dict:
        """Return real-time system health metrics"""
        status = self.get_status()
        
        # Calculate overall health score (0-100)
        available_ratio = status['available_keys'] / status['total_keys']
        avg_success_rate = sum(k['metrics']['success_rate'] for k in status['keys']) / status['total_keys']
        avg_response_time = sum(k['metrics']['avg_response_time'] for k in status['keys']) / status['total_keys']
        
        # Weighted health score
        health_score = (
            available_ratio * 40 +  # 40% weight on key availability
            avg_success_rate * 40 +  # 40% weight on success rate
            max(0, 20 - (avg_response_time * 2))  # 20% weight on response time (penalize slow responses)
        )
        
        return {
            'health_score': min(100, max(0, health_score)),
            'available_keys': status['available_keys'],
            'total_keys': status['total_keys'],
            'queries_per_minute': sum(k['metrics']['queries_per_minute'] for k in status['keys']),
            'queries_per_day': sum(k['metrics']['queries_per_day'] for k in status['keys']),
            'average_response_time': avg_response_time,
            'average_success_rate': avg_success_rate,
            'time_until_quota_reset': status['time_until_quota_reset']
        }

# Maintain backward compatibility by aliasing the original class name
RotatingGeminiClient = EnhancedRotatingGeminiClient

# Example usage
if __name__ == "__main__":
    # Initialize the enhanced client
    client = EnhancedRotatingGeminiClient()
    
    # Test the client
    print("Testing enhanced Gemini client...")
    response = client.ask_gemini("Hello, how are you?")
    print(f"Response: {response}")
    
    # Print system status
    print("\nSystem Status:")
    print(client.get_status())
    
    # Print system health
    print("\nSystem Health:")
    print(client.get_system_health())