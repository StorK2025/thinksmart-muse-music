"""Recycle a kiosk web process only at an explicit application boundary.

Normal links, OAuth redirects and navigation within an application are left to
WebKit. The shared WebsiteDataManager, cookies and local storage are never reset.
"""

from gi.repository import GLib, WebKit2


class AppNavigator:
    def __init__(self, view, classify, on_failure, on_status=None):
        self.view = view
        self.classify = classify
        self.on_failure = on_failure
        self.on_status = on_status or (lambda: None)
        self.pending_uri = None
        self.phase = None
        self.timer = 0
        self.generation = 0
        self.recycled = 0
        self.last_termination = ''
        view.connect('load-changed', self._load_changed)
        view.connect('web-process-terminated', self._terminated)

    @property
    def switching(self):
        return self.pending_uri is not None

    def navigate(self, destination):
        if self.switching:
            # A second tap chooses the latest destination without another recycle.
            self.pending_uri = destination
            return
        current = self.view.get_uri() or ''
        if not current or current == 'about:blank' or self.classify(current) == self.classify(destination):
            self.view.load_uri(destination)
            return

        self.generation += 1
        self.pending_uri = destination
        self.phase = 'unloading'
        self.view.stop_loading()
        # Let pagehide/unload and storage writes run before stopping the process.
        # about:blank stays in the old process and promptly stops its media/timers.
        self._arm(2000, self._recycle)
        self.view.load_uri('about:blank')
        self.on_status()

    def _cancel_timer(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def _arm(self, delay_ms, callback):
        self._cancel_timer()
        generation = self.generation

        def run():
            self.timer = 0
            if generation == self.generation and self.switching:
                callback()
            return False
        self.timer = GLib.timeout_add(delay_ms, run)

    def _recycle(self):
        if self.phase != 'unloading':
            return
        self.phase = 'recycling'
        # No web process can exist yet when a user taps immediately on startup.
        # This bounded fallback covers that case without waiting for a signal.
        self._arm(1500, self._finish)
        self.view.terminate_web_process()
        self.on_status()

    def _finish(self):
        if not self.switching:
            return
        self._cancel_timer()
        destination = self.pending_uri
        self.pending_uri = None
        self.phase = None
        self.recycled += 1
        self.view.load_uri(destination)
        self.on_status()

    def _load_changed(self, _view, event):
        if (self.phase == 'unloading' and event == WebKit2.LoadEvent.FINISHED
                and self.view.get_uri() == 'about:blank'):
            self._arm(60, self._recycle)
        self.on_status()

    def _terminated(self, _view, reason):
        self.last_termination = reason.value_nick
        if self.switching:
            self._arm(20, self._finish)
        elif reason != WebKit2.WebProcessTerminationReason.TERMINATED_BY_API:
            self.on_failure(reason)
        # A delayed acknowledgement of our own recycle must not navigate home.
        self.on_status()
