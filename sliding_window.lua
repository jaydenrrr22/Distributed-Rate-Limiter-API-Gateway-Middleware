local key = KEYS[1]
local now = tonumber(ARGV[1]) or 0
local window = tonumber(ARGV[2]) or 60
local limit = tonumber(ARGV[3]) or 5
local request_id = ARGV[4]

local clear_before = now - window

-- removing the timestamps older than the current window
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)

-- counting remaining requests in the window
local req_count = redis.call('ZCARD', key)

if req_count < limit then
    redis.call('ZADD', key, now, request_id)
    redis.call('EXPIRE', key, math.ceil(window))
    return {1, limit - req_count - 1}
else
    return {0, 0}
end

