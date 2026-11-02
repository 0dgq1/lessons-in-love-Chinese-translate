init python:
    import lil_bilingual

    lil_bilingual.runtime = lil_bilingual.Translator(
        config.gamedir, renpy.invoke_in_main_thread, renpy.restart_interaction)

    def bilingual_source(what):
        # Character.prefix_suffix has already interpolated this value. Repeating
        # interpolation would interpret literal brackets in names or dialogue.
        return renpy.filter_text_tags(what, allow=[]).replace('{{', '{')

    def bilingual_poll(source, retry=False):
        if lil_bilingual.runtime.current != lil_bilingual.runtime.key(source):
            widget = renpy.get_widget('say', 'bilingual_dialogue')
            if widget is not None:
                widget.yadjustment.change(0)
        lil_bilingual.runtime.activate(source, retry)
        position = renpy.game.context().current
        marker = (position, source)
        if lil_bilingual.runtime.lookahead_position != marker:
            lil_bilingual.runtime.lookahead_position = marker
            count = lil_bilingual.runtime.config.get('prefetch_lines', 3)
            try:
                node = renpy.game.script.lookup(position)
                future = [bilingual_source(text) for text in lil_bilingual.lookahead_texts(node, count)]
            except (KeyError, AttributeError):
                future = []
            lil_bilingual.runtime.prefetch(future)

    def bilingual_stop():
        lil_bilingual.runtime.suspend()

    def bilingual_font():
        candidate = lil_bilingual.runtime.config.get('font', 'bilingual_fonts/msyh.ttc')
        if isinstance(candidate, str) and renpy.loadable(candidate):
            return candidate
        return 'YuGothM.ttc'

screen bilingual_translation(what):
    $ bilingual_plain = bilingual_source(what)
    $ bilingual_value, bilingual_failed = lil_bilingual.runtime.view(bilingual_plain)
    timer 0.03 repeat True action Function(bilingual_poll, bilingual_plain)
    vbox:
        xsize gui.dialogue_width
        text bilingual_value.replace('{', '{{'):
            substitute False
            slow_cps 0
            font bilingual_font()
            size 26
            color gui.text_color
            xpos 0
            ypos 0
            xsize gui.dialogue_width - 30
        if bilingual_failed:
            textbutton "重试翻译":
                text_font bilingual_font()
                text_size 22
                action Function(bilingual_poll, bilingual_plain, True)
