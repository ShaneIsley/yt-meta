# (like 'like_count'), the client needs to fetch the full metadata for each
# video that passes the initial "fast" filters. This is more powerful but
# significantly slower.

# In this case, we are ONLY using a slow filter, so it will fetch full
# metadata for every video until it finds 5 that match.