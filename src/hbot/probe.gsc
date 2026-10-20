// Original observational bootstrap. Enable before map initialization.
// This module never changes bot goals, inputs, weapons, damage, or player state.
#namespace hbot_probe;

function autoexec __init__system__()
{
    if ( !getdvarint( @"hbot_probe_enabled", 0 ) )
    {
        return;
    }

    if ( isdefined( level.hbot_probe_started ) )
    {
        return;
    }

    level.hbot_probe_started = 1;
    level.hbot_shadow_records = [];
    iprintln( "[HBOT] probe loaded; waiting for match state" );
    level thread clear_on_game_end();
    level thread observe_match();
}

function clear_on_game_end()
{
    level waittill( "game_ended" );
    level.hbot_shadow_records = [];
}

function observe_match()
{
    level endon( "game_ended" );

    for ( attempt = 0; attempt < 120; attempt++ )
    {
        if ( isdefined( level.players ) && level.players.size > 0 && isdefined( level.teambased ) )
        {
            break;
        }
        wait 0.25;
    }
    if ( !isdefined( level.players ) || !isdefined( level.teambased ) )
    {
        iprintln( "[HBOT] match state timeout; observer stopped" );
        return;
    }
    mode = getgametype();
    if ( !hbot_mode::supports_tdm( mode, level.teambased, level.players.size ) )
    {
        iprintln( "[HBOT] unsupported: mode=" + mode + " team=" + level.teambased + " players=" + level.players.size );
        return;
    }
    shadow_enabled = getdvarint( @"hbot_memory_enabled", 0 );
    diagnostics_enabled = getdvarint( @"hbot_debug_enabled", 0 );
    bot_ordinal = getdvarint( @"hbot_debug_bot", 1 );
    human_ordinal = getdvarint( @"hbot_debug_human", 1 );
    if ( bot_ordinal < 1 || bot_ordinal > 12 )
    {
        bot_ordinal = 1;
    }
    if ( human_ordinal < 1 || human_ordinal > 12 )
    {
        human_ordinal = 1;
    }
    if ( shadow_enabled || getdvarint( @"hbot_memory_selftest", 0 ) )
    {
        report = hbot_contracts::run_memory_contracts();
        iprintln( "[HBOT] memory selftest passed=" + report.passed + " failed=" + report.failed + " first_failure=" + report.first_failure );
        if ( report.failed > 0 )
        {
            return;
        }
    }
    iprintln( "[HBOT] TDM observer active; behavior_control=0 memory=" + shadow_enabled );
    if ( diagnostics_enabled && !shadow_enabled )
    {
        iprintln( "[HBOT] focus unavailable: enable memory before map initialization" );
    }
    observer_cursor = 0;
    next_report = 0;
    next_focus_report = 0;

    for ( ;; )
    {
        if ( !hbot_mode::supports_tdm( getgametype(), level.teambased, level.players.size ) )
        {
            level.hbot_shadow_records = [];
            iprintln( "[HBOT] scope changed; observer stopped" );
            return;
        }
        hbot_perception::cleanup_records();
        bots = 0;
        humans = 0;
        alive_bots = 0;
        observers = [];

        foreach ( player in level.players )
        {
            if ( !isdefined( player ) )
            {
                continue;
            }

            if ( isbot( player ) )
            {
                bots++;
                if ( isalive( player ) )
                {
                    alive_bots++;
                    if ( hbot_perception::eligible_player( player ) )
                    {
                        observers[ observers.size ] = player;
                    }
                }
            }
            else
            {
                humans++;
            }
        }

        now_ms = gettime();
        if ( shadow_enabled && observers.size > 0 )
        {
            observer_cursor = observer_cursor % observers.size;
            hbot_perception::scan_observer( observers[ observer_cursor ], level.players, now_ms, diagnostics_enabled );
            observer_cursor++;
        }
        if ( now_ms >= next_report )
        {
            contacts = 0;
            foreach ( record in level.hbot_shadow_records )
            {
                if ( isdefined( record ) && record.active )
                {
                    contacts += hbot_memory::count_contacts( record.memory, now_ms );
                }
            }
            iprintln( "[HBOT] bots=" + bots + " alive_bots=" + alive_bots + " humans=" + humans + " memories=" + contacts );
            next_report = now_ms + 5000;
        }
        if ( diagnostics_enabled && shadow_enabled && now_ms >= next_focus_report )
        {
            hbot_diagnostics::report_focus( level.players, bot_ordinal, human_ordinal, now_ms );
            next_focus_report = now_ms + 1000;
        }
        wait 0.05;
    }
}
