// The native war gametype is the initial TDM research allowlist entry.
#namespace hbot_mode;

function supports_tdm( mode, teambased, player_count )
{
    if ( !isdefined( mode ) || !isdefined( teambased ) || !teambased )
    {
        return 0;
    }
    return mode == "war" && player_count > 0 && player_count <= 12;
}
