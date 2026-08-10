import Redis from "ioredis";

// Fail gracefully if REDIS_URL is not provided or if connection fails.
const redisUrl = process.env.REDIS_URL || "redis://127.0.0.1:6379/0";
const redis = new Redis(redisUrl, {
  maxRetriesPerRequest: 1,
  retryStrategy(times) {
    if (times > 3) {
      return null;
    }
    return Math.min(times * 100, 3000);
  },
  enableOfflineQueue: false,
});

redis.on("error", (err) => {
  console.warn("Redis rate limiter connection error:", err.message);
});

export async function checkRateLimit(
  ip: string,
  action: string,
  limit: number,
  windowSec: number
): Promise<{ success: boolean; limit: number; remaining: number; reset: number }> {
  try {
    const key = `ratelimit:${action}:${ip}`;
    const current = await redis.incr(key);
    
    if (current === 1) {
      await redis.expire(key, windowSec);
    }
    
    const ttl = await redis.ttl(key);
    const reset = Math.floor(Date.now() / 1000) + (ttl > 0 ? ttl : windowSec);
    
    return {
      success: current <= limit,
      limit,
      remaining: Math.max(0, limit - current),
      reset,
    };
  } catch (error) {
    // Fail open: If Redis is down, do not permanently lock out legitimate users.
    return {
      success: true,
      limit,
      remaining: 1,
      reset: Math.floor(Date.now() / 1000) + windowSec,
    };
  }
}
