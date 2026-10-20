// Pure shadow policy: filtered memory and sampled evidence in, intent out.
#namespace hbot_decision;

function bounded_ms( value, maximum, fallback )
{
    if ( !isdefined( value ) || !isnumber( value ) || value < 1 || value > maximum || int( value ) != value )
    {
        return fallback;
    }
    return value;
}

function create_controller( reaction_ms, search_ms, stale_ms )
{
    control = spawnstruct();
    control.reaction_ms = bounded_ms( reaction_ms, 2000, 250 );
    control.search_ms = bounded_ms( search_ms, 10000, 3000 );
    control.stale_ms = bounded_ms( stale_ms, 5000, 2000 );
    reset( control );
    return control;
}

function clear_focus( control )
{
    control.state = "idle";
    control.target_id = undefined;
    control.reaction_started_at = -1;
    control.last_positive_at = -1;
    control.search_deadline = -1;
}

function reset( control )
{
    clear_focus( control );
    control.last_tick = -1;
}

function acquire( control, target_id, now_ms )
{
    control.state = "reacting";
    control.target_id = target_id;
    control.reaction_started_at = now_ms;
    control.last_positive_at = now_ms;
    control.search_deadline = -1;
}

function snapshot( control, memory, now_ms )
{
    intent = spawnstruct();
    intent.state = control.state;
    intent.kind = "none";
    intent.target_id = control.target_id;
    intent.position = undefined;
    intent.reaction_remaining_ms = 0;
    intent.search_remaining_ms = 0;
    if ( control.state == "reacting" )
    {
        intent.kind = "wait";
        remaining = control.reaction_started_at + control.reaction_ms - now_ms;
        if ( remaining > 0 )
        {
            intent.reaction_remaining_ms = remaining;
        }
    }
    else if ( control.state == "tracking" || control.state == "searching" )
    {
        contact = hbot_memory::recall( memory, control.target_id, now_ms );
        if ( isdefined( contact ) )
        {
            intent.position = contact.position;
            intent.kind = "observe";
            if ( control.state == "searching" )
            {
                intent.kind = "search";
                intent.search_remaining_ms = control.search_deadline - now_ms;
            }
        }
    }
    return intent;
}

function update( control, memory, samples, now_ms )
{
    if ( !isdefined( now_ms ) || !isnumber( now_ms ) || now_ms < 0 || int( now_ms ) != now_ms || now_ms < control.last_tick )
    {
        hbot_memory::clear( memory );
        reset( control );
        return snapshot( control, memory, 0 );
    }
    hbot_memory::advance( memory, now_ms );
    control.last_tick = now_ms;
    contact = undefined;
    if ( isdefined( control.target_id ) )
    {
        contact = hbot_memory::recall( memory, control.target_id, now_ms );
        if ( !isdefined( contact ) || now_ms - control.last_positive_at >= memory.ttl_ms )
        {
            clear_focus( control );
        }
    }
    focused_sample = -1;
    best_visible = undefined;
    foreach ( sample in samples )
    {
        if ( !isdefined( sample ) || !isdefined( sample.target_id ) || !isnumber( sample.target_id ) || sample.target_id < 0 || sample.target_id > 2047 || int( sample.target_id ) != sample.target_id || !isdefined( sample.at_ms ) || sample.at_ms != now_ms || !isdefined( sample.visible ) || ( sample.visible != 0 && sample.visible != 1 ) )
        {
            continue;
        }
        if ( sample.visible )
        {
            observed = hbot_memory::recall( memory, sample.target_id, now_ms );
            if ( !isdefined( observed ) || observed.seen_at != now_ms )
            {
                continue;
            }
            if ( !isdefined( best_visible ) || sample.target_id < best_visible )
            {
                best_visible = sample.target_id;
            }
        }
        if ( isdefined( control.target_id ) && sample.target_id == control.target_id )
        {
            focused_sample = sample.visible;
        }
    }
    stale = now_ms - control.last_positive_at >= control.stale_ms;
    if ( focused_sample == 1 )
    {
        control.last_positive_at = now_ms;
    }
    if ( control.state == "reacting" )
    {
        if ( focused_sample == 0 || stale )
        {
            clear_focus( control );
        }
        else if ( focused_sample == 1 && now_ms - control.reaction_started_at >= control.reaction_ms )
        {
            control.state = "tracking";
        }
    }
    else if ( control.state == "tracking" && ( focused_sample == 0 || stale ) )
    {
        control.state = "searching";
        control.search_deadline = now_ms + control.search_ms;
        expires_at = contact.seen_at + memory.ttl_ms;
        if ( control.search_deadline > expires_at )
        {
            control.search_deadline = expires_at;
        }
    }
    if ( control.state == "searching" && now_ms >= control.search_deadline )
    {
        clear_focus( control );
    }
    if ( isdefined( best_visible ) && ( control.state == "idle" || control.state == "searching" ) )
    {
        acquire( control, best_visible, now_ms );
    }
    return snapshot( control, memory, now_ms );
}
