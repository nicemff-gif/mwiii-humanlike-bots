// Runtime adapter: only a positive visibility result exports a target position.
#namespace hbot_perception;

function eligible_player( player )
{
    if ( !isdefined( player ) || !isplayer( player ) || !isalive( player ) )
    {
        return 0;
    }
    if ( !isdefined( player.sessionstate ) || player.sessionstate != "playing" || !isdefined( player.team ) )
    {
        return 0;
    }
    return player.team == "allies" || player.team == "axis";
}

function angle_delta( desired, current )
{
    error = desired - current;
    while ( error > 180 )
    {
        error -= 360;
    }
    while ( error < -180 )
    {
        error += 360;
    }
    return error;
}

function sample_visible( observer, target )
{
    if ( !eligible_player( observer ) || !eligible_player( target ) || observer == target || observer.team == target.team )
    {
        return undefined;
    }
    eye = observer geteye();
    view = observer getplayerangles();
    if ( !isvector( eye ) || !isvector( view ) || !isdefined( target.origin ) || !isvector( target.origin ) )
    {
        return undefined;
    }
    point = target.origin + ( 0, 0, 46 );
    if ( distancesquared( eye, point ) > 1800 * 1800 )
    {
        return undefined;
    }
    desired = vectortoangles( point - eye );
    if ( abs( angle_delta( desired[ 1 ], view[ 1 ] ) ) > 60 || abs( angle_delta( desired[ 0 ], view[ 0 ] ) ) > 45 )
    {
        return undefined;
    }
    if ( !sighttracepassed( eye, point, 0, observer ) )
    {
        return undefined;
    }
    observation = spawnstruct();
    observation.target_id = target getentitynumber();
    observation.position = target.origin;
    return observation;
}

function clear_on_death( record )
{
    self endon( "hbot_shadow_life" );
    self endon( "disconnect" );
    level endon( "game_ended" );
    self waittill( "death" );
    hbot_memory::clear( record.memory );
    hbot_decision::reset( record.control );
    record.pending_samples = [];
    record.active = 0;
}

function scan_observer( observer, players, now_ms, diagnostics_enabled )
{
    key = observer getentitynumber();
    record = level.hbot_shadow_records[ key ];
    if ( !isdefined( record ) || !record.active || record.entity != observer || record.team != observer.team )
    {
        record = spawnstruct();
        record.entity = observer;
        record.slot = key;
        record.team = observer.team;
        record.active = 1;
        record.cursor = 0;
        record.last_samples = [];
        record.memory = hbot_memory::create_memory( 4000, 16 );
        record.control = hbot_decision::create_controller( 250, 3000, 2000 );
        record.pending_samples = [];
        level.hbot_shadow_records[ key ] = record;
        observer notify( "hbot_shadow_life" );
        observer thread clear_on_death( record );
    }
    hbot_memory::advance( record.memory, now_ms );
    scanned = 0;
    samples = 0;
    record.last_visible_count = 0;
    while ( scanned < players.size && samples < 2 )
    {
        record.cursor = record.cursor % players.size;
        candidate = players[ record.cursor ];
        record.cursor++;
        scanned++;
        if ( !eligible_player( candidate ) || candidate == observer || candidate.team == observer.team )
        {
            continue;
        }
        samples++;
        observation = sample_visible( observer, candidate );
        sample = spawnstruct();
        sample.target_id = candidate getentitynumber();
        sample.at_ms = now_ms;
        sample.visible = isdefined( observation );
        record.pending_samples[ record.pending_samples.size ] = sample;
        if ( diagnostics_enabled )
        {
            sample.result = "rejected";
            if ( isdefined( observation ) )
            {
                sample.result = "visible";
            }
            record.last_samples[ candidate getentitynumber() ] = sample;
        }
        if ( isdefined( observation ) )
        {
            hbot_memory::record_visible( record.memory, observation.target_id, observation.position, now_ms );
            record.last_visible_count++;
        }
    }
}

function cleanup_records()
{
    foreach ( record in level.hbot_shadow_records )
    {
        if ( isdefined( record ) && ( !record.active || !eligible_player( record.entity ) ) )
        {
            hbot_memory::clear( record.memory );
            hbot_decision::reset( record.control );
            record.active = 0;
            level.hbot_shadow_records[ record.slot ] = undefined;
        }
    }
}
