// Pure memory domain: no entities, engine time, or hidden-world reads.
#namespace hbot_memory;

function create_memory( ttl_ms, capacity )
{
    if ( !isdefined( ttl_ms ) || !isnumber( ttl_ms ) || ttl_ms < 1 || ttl_ms > 15000 )
    {
        ttl_ms = 4000;
    }
    if ( !isdefined( capacity ) || !isnumber( capacity ) || capacity < 1 || capacity > 32 )
    {
        capacity = 16;
    }
    capacity = int( capacity );
    memory = spawnstruct();
    memory.ttl_ms = ttl_ms;
    memory.capacity = capacity;
    memory.last_tick = -1;
    memory.entries = [];
    for ( i = 0; i < capacity; i++ )
    {
        entry = spawnstruct();
        entry.active = 0;
        memory.entries[ i ] = entry;
    }
    return memory;
}

function clear( memory )
{
    foreach ( entry in memory.entries )
    {
        entry.active = 0;
        entry.last_position = undefined;
        entry.target_id = undefined;
    }
    memory.last_tick = -1;
}

function advance( memory, now_ms )
{
    if ( !isdefined( now_ms ) || !isnumber( now_ms ) || now_ms < 0 || int( now_ms ) != now_ms )
    {
        clear( memory );
        return 0;
    }
    if ( now_ms < memory.last_tick )
    {
        clear( memory );
    }
    memory.last_tick = now_ms;
    foreach ( entry in memory.entries )
    {
        if ( entry.active && now_ms >= entry.expires_at )
        {
            entry.active = 0;
            entry.last_position = undefined;
            entry.target_id = undefined;
        }
    }
    return 1;
}

function record_visible( memory, target_id, position, now_ms )
{
    if ( !advance( memory, now_ms ) )
    {
        return 0;
    }
    if ( !isdefined( target_id ) || !isnumber( target_id ) || target_id < 0 || target_id > 2047 || int( target_id ) != target_id || !isdefined( position ) || !isvector( position ) )
    {
        return 0;
    }
    selected = undefined;
    foreach ( entry in memory.entries )
    {
        if ( entry.active && entry.target_id == target_id )
        {
            selected = entry;
            break;
        }
    }
    if ( !isdefined( selected ) )
    {
        foreach ( entry in memory.entries )
        {
            if ( !entry.active )
            {
                selected = entry;
                break;
            }
        }
    }
    if ( !isdefined( selected ) )
    {
        selected = memory.entries[ 0 ];
        foreach ( entry in memory.entries )
        {
            if ( entry.seen_at < selected.seen_at )
            {
                selected = entry;
            }
        }
    }
    selected.active = 1;
    selected.target_id = target_id;
    selected.last_position = position;
    selected.seen_at = now_ms;
    selected.expires_at = now_ms + memory.ttl_ms;
    return 1;
}

function recall( memory, target_id, now_ms )
{
    if ( !advance( memory, now_ms ) )
    {
        return undefined;
    }
    foreach ( entry in memory.entries )
    {
        if ( entry.active && entry.target_id == target_id )
        {
            contact = spawnstruct();
            contact.target_id = entry.target_id;
            contact.position = entry.last_position;
            contact.seen_at = entry.seen_at;
            contact.age_ms = now_ms - entry.seen_at;
            contact.confidence = 1 - contact.age_ms / ( memory.ttl_ms * 1.0 );
            return contact;
        }
    }
    return undefined;
}

function count_contacts( memory, now_ms )
{
    if ( !advance( memory, now_ms ) )
    {
        return 0;
    }
    count = 0;
    foreach ( entry in memory.entries )
    {
        if ( entry.active )
        {
            count++;
        }
    }
    return count;
}
