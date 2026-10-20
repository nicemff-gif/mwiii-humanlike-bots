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
    level thread observe_match();
}

function observe_match()
{
    level endon( "game_ended" );

    while ( !isdefined( level.players ) )
    {
        wait 0.25;
    }

    iprintln( "[HBOT] observer active; behavior control is not enabled" );

    for ( ;; )
    {
        bots = 0;
        humans = 0;
        alive_bots = 0;

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
                }
            }
            else
            {
                humans++;
            }
        }

        iprintln( "[HBOT] bots=" + bots + " alive_bots=" + alive_bots + " humans=" + humans );
        wait 10;
    }
}
