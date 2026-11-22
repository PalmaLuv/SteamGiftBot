"""One requests session per site connected with pasted browser cookies
(IndieGala, OpiumPulses), kept from pass to pass.

A fresh session every pass started from the paste each time and threw away
whatever the site had refreshed since (Set-Cookie: Incapsula's cookies, a
renewed sign-in), so the farm kept sending the browser's old values. Now the
session lives on while the pasted text and the User-Agent stay the same. The
values the site refreshed are written down in farm.json, next to the paste
rather than into it (a cURL command or an export rewritten by the farm would
no longer be what the user pasted), and put over the paste when a session has
to be built again, after a restart. They belong to that one paste: a new one
starts clean. When the sign-in cookie's expiry is known, the panel shows it
and Telegram is told a few days before it."""
import hashlib
import re
import time

from datetime import datetime

from steamgiftbot.farm.base import (PlatformError, buildSession, cookieExpiries, parseCookies,
                                    userAgentFrom)

# The site's record in farm.json that keeps the refreshed cookies.
KEPT = 'sessionCookies'
# The reminder comes this long before the sign-in cookie expires.
EXPIRY_NOTICE = 3 * 86400


# Which paste a record or a session belongs to, without keeping the paste twice.
def pasteId(*texts):
    return hashlib.sha256('\n'.join(str(text or '') for text in texts).encode()).hexdigest()[:16]


class KeptSession:
    """Mixed into a Platform before it: class Site(KeptSession, Platform)."""
    # Where the pasted cookies are set.
    sessionDomain = ''
    # The cookies that keep the account signed in; when the last of them
    # expires, the site will ask to sign in again.
    signInCookie = re.compile(r'(?!)')

    session      = None
    sessionId    = None     # the paste and User-Agent the session was built from
    sessionPaste = None     # the paste alone, for the refreshed cookies
    isSandbox    = False

    # A dry run or a connection check gets a session of its own and writes
    # nothing back: a check tries cookies that are not saved yet.
    def sandbox(self):
        clone = super().sandbox()
        clone.session = clone.sessionId = clone.sessionPaste = None
        clone.isSandbox = True
        return clone

    def keptRecord(self, paste):
        record = self.manager.platformEntry(self.key).get(KEPT) or {}
        return record if paste and record.get('paste') == pasteId(paste) else {}

    def dropKept(self):
        with self.manager.lock:
            if self.manager.platformEntry(self.key).pop(KEPT, None) is None:
                return
        self.manager.saveFarm()

    # True when a new session was built, so the site can set its headers.
    def openSession(self, conf):
        paste = conf.get('cookie') or ''
        ident = pasteId(paste, conf.get('user_agent'))
        if self.session is not None and self.sessionId == ident:
            return False
        cookies = parseCookies(paste)
        if not cookies:
            raise PlatformError("не задан cookie")
        record = self.keptRecord(paste)
        if not record and not self.isSandbox:
            # Values refreshed for an older paste are of no use any more.
            self.dropKept()
        cookies.update({name: value for name, value in (record.get('values') or {}).items()
                        if name in cookies})
        self.session = buildSession(userAgentFrom(paste) or conf.get('user_agent'),
                                    cookies, self.sessionDomain)
        self.sessionId, self.sessionPaste = ident, pasteId(paste)
        return True

    # After a pass: the pasted cookies the site has given new values, and the
    # expiries it sent with the sign-in ones. Names only in the log, never
    # values. Nothing is written when nothing changed.
    def keepCookies(self):
        if self.isSandbox or self.session is None or self.sessionPaste is None:
            return
        paste = self.settings().get('cookie') or ''
        if pasteId(paste) != self.sessionPaste:
            return      # a new paste was saved during the pass
        pasted = parseCookies(paste)
        values, expires = {}, {}
        for cookie in getattr(self.session, 'cookies', None) or ():
            if cookie.name in pasted:
                # The newest copy counts, as in cookieValue().
                values[cookie.name] = cookie.value
            if cookie.expires and self.signInCookie.fullmatch(cookie.name):
                expires[cookie.name] = int(cookie.expires)
        changed = {name: value for name, value in values.items() if value != pasted[name]}
        record = self.keptRecord(paste)
        expires = {**(record.get('expires') or {}), **expires}
        fresh = {'paste': self.sessionPaste, 'values': changed, 'expires': expires}
        if not changed and not expires:
            if record:
                self.dropKept()
            return
        if fresh == record:
            return
        renewed = sorted(name for name, value in changed.items()
                         if (record.get('values') or {}).get(name) != value)
        if renewed:
            self.debug(f"Сайт обновил cookie: {', '.join(renewed)}")
        self.manager.updatePlatformEntry(self.key, **{KEPT: fresh})

    # When the sign-in cookie expires (Unix seconds), from the paste and from
    # what the site has sent since; None when neither says.
    def cookieExpiry(self, paste=None):
        paste = self.settings().get('cookie') if paste is None else paste
        if not paste:
            return None
        known = cookieExpiries(paste)
        known.update(self.keptRecord(paste).get('expires') or {})
        found = [moment for name, moment in known.items() if self.signInCookie.fullmatch(name)]
        return max(found) if found else None

    # One card per expiry, EXPIRY_NOTICE before it. An expiry the site moves
    # forward (it renewed the cookie) is a new one and gets its own card when
    # its time comes.
    def remindExpiry(self, now=None):
        if self.isSandbox:
            return False
        moment = self.cookieExpiry()
        now = now or time.time()
        if not moment or moment <= now or moment - now > EXPIRY_NOTICE:
            return False
        state = self.manager.state
        if state.value(self.key, 'cookie_expiry_told') == moment:
            return False
        state.setFlag(self.key, 'cookie_expiry_told', moment)
        when = datetime.fromtimestamp(moment, self.manager.zone())
        self.notify('', '🔑', title='COOKIE СКОРО ИСТЕЧЁТ',
                    headline=f"Вход на сайт истекает {when:%d.%m.%Y %H:%M}",
                    note="Войдите на сайт в браузере, скопируйте запрос заново и подключите "
                         "площадку: иначе после этого срока сайт перестанет узнавать ферму.",
                    buttons=[("Подключить заново",
                              self.manager.panelLink(f'/connect/{self.key}'))])
        return True

    # The end of every pass, a failed one too: what the site refreshed is kept
    # either way, and a problem with that never stops the pass.
    def afterPass(self):
        try:
            self.keepCookies()
        except Exception as error:
            self.warn(f"Cookie не сохранены: {type(error).__name__}")

    def disconnect(self):
        super().disconnect()
        self.dropKept()
        self.session = self.sessionId = self.sessionPaste = None

    def snapshot(self):
        data = super().snapshot()
        try:
            data['cookieExpires'] = self.cookieExpiry()
        except Exception:
            data['cookieExpires'] = None
        return data
