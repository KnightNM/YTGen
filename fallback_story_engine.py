"""Curated offline stories used only when remote generation cannot pass validation."""

from __future__ import annotations

from typing import Any


FALLBACK_STORIES: tuple[dict[str, Any], ...] = (
    {
        "title": "The Voice Above the Ceiling",
        "description": "A routine closing shift exposed who had been living above us. An original fictional horror story. #horror #scarystory #creepy #shorts",
        "narration_segments": [
            "I managed a small pharmacy, and every night at 9:15 the fire alarm above aisle six whispered my first name.",
            "The panel showed no fault, so my boss blamed an old speaker and told me to keep closing normally.",
            "On Friday, I heard the whisper answer a customer who had already left, using the customer’s exact voice.",
            "I locked the front door, called the building manager, and waited outside where the security camera could see me.",
            "The contractor opened the ceiling hatch and found blankets, food wrappers, and a baby monitor wired beside the alarm speaker.",
            "Police arrested a former maintenance worker in the crawlspace; he had recorded customers for months and played their voices after closing.",
            "The pharmacy replaced the ceiling and cameras, and I transferred stores, but hearing my own recorded voice in court was worse than any ghost.",
        ],
        "image_prompts": [
            "same tired male pharmacy manager in his thirties wearing a blue work vest beneath a ceiling fire alarm in empty aisle six at night",
            "same manager examining a normal alarm control panel while an impatient older boss gestures dismissively in the pharmacy office",
            "same manager frozen beside stocked shelves as a tiny ceiling speaker crackles after the last customer exits",
            "same manager outside locked glass pharmacy doors calling for help beneath a visible security camera",
            "contractor opening a ceiling hatch above aisle six while the manager watches from a safe distance, blankets and wrappers visible inside",
            "police leading a disheveled former maintenance worker from the cramped ceiling space, baby monitor and recording equipment visible",
            "same manager seated in a plain courtroom listening to an evidence recorder, disturbed but safe, incident conclusively over",
        ],
    },
    {
        "title": "Someone Was Using the Empty Room",
        "description": "My first week at a roadside motel ended with a room that was never rented. An original fictional horror story. #horror #motel #scarystory #shorts",
        "narration_segments": [
            "During my first week clerking at a roadside motel, room 214 kept adding one breakfast charge after every midnight shift.",
            "The room had been closed for mold repairs, and its only key stayed inside a sealed envelope beneath my register.",
            "I checked the hallway camera and saw the ice machine door swing open each night, though nobody appeared in the corridor.",
            "Instead of investigating alone, I called the owner and the county deputy, then watched the live monitor from the locked office.",
            "The deputy found a narrow service door behind the ice machine leading through the wall into room 214.",
            "The owner’s adult son had been sleeping there and using an old staff code to charge food without appearing at the front desk.",
            "They changed every lock and closed the passage permanently; I quit because the owner had known his son was missing and never warned me.",
        ],
        "image_prompts": [
            "same young female motel clerk with a green cardigan studying a breakfast charge on an old computer at midnight",
            "same clerk holding a sealed room-key envelope beneath the front register, repair notice for room 214 nearby",
            "grainy hallway monitor showing an ice machine door opening in an otherwise empty motel corridor while the clerk watches",
            "same clerk safely inside a locked motel office calling the owner and deputy while watching security screens",
            "uniformed deputy pulling open a narrow hidden service door behind the ice machine as the clerk observes from far back",
            "disheveled adult man discovered inside closed motel room 214 beside stolen food trays and an old staff keypad",
            "workers permanently boarding the hidden passage while the same clerk leaves in daylight carrying a small bag",
        ],
    },
    {
        "title": "The Breathing Under the Stage",
        "description": "A school rehearsal revealed why the auditorium never sounded empty. An original fictional horror story. #horror #school #creepy #shorts",
        "narration_segments": [
            "I volunteered to lock my daughter’s school auditorium after rehearsal, usually a boring ten-minute job.",
            "That Tuesday, the microphone picked up slow breathing whenever I crossed the center of the empty stage.",
            "I switched the microphone off, but the breathing continued through a floor vent beneath my shoes.",
            "I took my daughter outside, called the custodian and police, and left every auditorium light on.",
            "They opened the orchestra-pit access and found a confused elderly man hiding among old costumes and canned food.",
            "He had wandered from a nearby care home three days earlier and entered through a loading door that never latched properly.",
            "He returned safely to his family, the school replaced the door, and I stopped mistaking a frightening sound for something supernatural.",
        ],
        "image_prompts": [
            "same concerned mother in her forties holding auditorium keys after a school rehearsal while her teenage daughter waits nearby",
            "same mother crossing the center of an empty school stage as a microphone meter moves with mysterious breathing",
            "close view of the mother standing over a dark floor vent while the switched-off microphone rests nearby",
            "same mother and daughter safely outside the lit auditorium calling the custodian and police",
            "custodian and police opening orchestra-pit access and discovering an elderly man among dusty costumes and canned food",
            "elderly lost man being helped from the auditorium beside a faulty loading door while the mother watches",
            "repaired loading door in daylight as the mother and daughter leave the now-safe school auditorium",
        ],
    },
    {
        "title": "The Calls From My Closed Office",
        "description": "My office extension kept calling after everyone went home. An original fictional horror story. #horror #office #scarystory #shorts",
        "narration_segments": [
            "I handled payroll for a warehouse, and my desk extension began calling my mobile every night at exactly 11:40.",
            "Each voicemail contained chair wheels, keyboard taps, and someone quietly reading employee addresses from my screen.",
            "I changed my password from home and reported it, but building security insisted the alarm logs showed an empty office.",
            "The next evening, police and our IT manager entered together while I watched remotely from a secure video call.",
            "They found a wireless keyboard receiver hidden inside my desktop and fresh ceiling dust above the supply cabinet.",
            "A contract cleaner had copied an access badge and climbed through adjoining ceiling panels to collect personal information.",
            "He was arrested with the copied files, every affected employee was notified, and the company rebuilt access controls before we returned.",
        ],
        "image_prompts": [
            "same female payroll worker in her thirties at home staring at repeated 11:40 calls from her office extension",
            "same worker listening fearfully to a voicemail while a visual memory shows an empty office chair and glowing employee database",
            "same worker changing her password on a home laptop while speaking to skeptical warehouse security",
            "police and an IT manager entering the dark payroll office together as the worker watches safely through a video call",
            "IT manager discovering a tiny wireless receiver inside the desktop with fresh ceiling dust above a supply cabinet",
            "police finding a contract cleaner in ceiling panels with a copied badge and storage drive",
            "employees returning to a bright secured office with replaced access panels after the arrest and formal notification",
        ],
    },
)


def select_offline_story(previous_titles: set[str]) -> dict[str, Any]:
    """Choose the first curated story not present in recent history."""
    for story in FALLBACK_STORIES:
        if story["title"] not in previous_titles:
            return story
    # Remote generation has failed after the curated set was exhausted; cycling is
    # preferable to fabricating an unchecked story, and uniqueness validation still runs.
    return FALLBACK_STORIES[len(previous_titles) % len(FALLBACK_STORIES)]

