// Opt-in readout. Position output comes exclusively from the memory snapshot.
#namespace hbot_diagnostics;

function select_player( players, want_bot, ordinal )
{
    found = 0;
    foreach ( player in players )
    {
        if ( !isdefined( player ) || !isplayer( player ) || isbot( player ) != want_bot )
        {
            continue;
        }
        found++;
        if ( found == ordinal )
        {
            return player;
        }
    }
    return undefined;
}

function report_focus( players, bot_ordinal, human_ordinal, now_ms )
{
    observer = select_player( players, 1, bot_ordinal );
    target = select_player( players, 0, human_ordinal );
    label = "[HBOT focus] bot#" + bot_ordinal + " human#" + human_ordinal;
    if ( !isdefined( observer ) || !isdefined( target ) )
    {
        iprintln( label + " missing_player" );
        return;
    }
    if ( !hbot_perception::eligible_player( observer ) )
    {
        iprintln( label + " observer_inactive memory=none" );
        return;
    }
    if ( !hbot_perception::eligible_player( target ) )
    {
        iprintln( label + " target_inactive" );
        return;
    }
    if ( observer.team == target.team )
    {
        iprintln( label + " same_team" );
        return;
    }
    record = level.hbot_shadow_records[ observer getentitynumber() ];
    if ( !isdefined( record ) || !record.active || record.entity != observer || record.team != observer.team )
    {
        iprintln( label + " observer_pending memory=none" );
        return;
    }
    target_id = target getentitynumber();
    if ( isdefined( record.intent ) )
    {
        intent = record.intent;
        focused = isdefined( intent.target_id ) && intent.target_id == target_id;
        iprintln( "[HBOT plan] state=" + intent.state + " kind=" + intent.kind + " focused=" + focused + " reaction_ms=" + intent.reaction_remaining_ms + " search_ms=" + intent.search_remaining_ms );
    }
    sample = record.last_samples[ target_id ];
    if ( isdefined( sample ) )
    {
        sample_age_ms = now_ms - sample.at_ms;
        iprintln( label + " sample=" + sample.result + " sample_age_ms=" + sample_age_ms );
    }
    else
    {
        iprintln( label + " sample=pending" );
    }
    contact = hbot_memory::recall( record.memory, target_id, now_ms );
    if ( !isdefined( contact ) )
    {
        iprintln( "[HBOT memory] none" );
        return;
    }
    iprintln( "[HBOT memory] last=(" + int( contact.position[ 0 ] ) + "," + int( contact.position[ 1 ] ) + "," + int( contact.position[ 2 ] ) + ") age_ms=" + contact.age_ms + " confidence_pct=" + int( contact.confidence * 100 ) );
}
