# Multiple profiles

A profile (учётка) is a person with their own accounts on the sites: you, a
brother, a sister. Each profile has its own set of sites, and each site in it
is a separate card with its own cookies, settings, daily limits, history, log
and wins. They work independently: your brother's SteamGifts waits for points
while yours is entering giveaways.

> **Read the site's rules.** SteamGifts, IndieGala and others usually allow
> one account per person, and the site may link accounts that come from the
> same IP and ban them together. Connect accounts of different people only,
> and at your own risk.

## Creating a profile

1. Open Sites (Площадки). At the top are the profile tabs: Main (Основная)
   and every profile you created, with the number of connected sites.
2. **"+ New profile" («+ Новая учётка»)**: a name ("Brother") and, if you
   have [ArchiSteamFarm](ArchiSteamFarm-EN.md), this profile's Steam, i.e. its
   bot in ASF. You can pick the bot later too.
3. "Create and open" («Создать и открыть») opens the empty profile.

## Editing a profile

In the header of the open profile, click **Edit (Изменить)** or the profile's
name. The header turns into a form: the name and the Steam bot in ASF. "Save"
(«Сохранить») or Enter saves it; "Cancel" («Отмена») or Esc restores what was
there. The name must not be empty and must not match another profile's name;
if something is wrong, the error appears right under the field. The new name
shows up at once on the tab, on the site cards, in the log and in the wins.

## Connecting sites to a profile

1. At the bottom of the open profile is **"Connect to this profile"
   («Подключить в эту учётку»)**: every site that the profile does not have
   yet.
2. **Sign in to the site with this profile's account in another browser
   profile or in an incognito window.** If you copy the request from a window
   where someone else's account is open, you get their cookies, and the farm
   replies that this account is already connected.
3. Copy the request as cURL and paste it, just as in a
   [normal connection](Connecting-Sites-EN.md). You may close the window, but
   do not sign out: signing out resets the cookies.
4. "Test connection" («Проверить подключение»). The farm asks the site whose
   account it is and creates the card only if the site recognised the
   cookies. A failed attempt leaves nothing behind.
5. Choose a preset and "Save and start" («Сохранить и запустить»).

Within one profile, each site can be connected once. The same site account
cannot end up in two profiles: the farm compares the account name on the site
(on SteamGifts it is visible in the profile link in the header).

## Telling them apart

While there is only one profile, cards are simply called "IndieGala". Once
there are others, the profile name is added to the title: "IndieGala · Main",
"IndieGala · Brother". That is how they appear in the overview, the log, the
history, the wins and the Telegram messages. On the Overview (Обзор), sites
are grouped by profile. The dot on the cards of other profiles is a lighter
shade of the site's colour. Wins (Выигрыши) has a profile filter, and the
"← Profile …" («← Учётка …») link on a site's page leads back to its profile.

In [Telegram commands](Telegram-EN.md), `/pause indiegala` stops IndieGala in
every profile; you can name a single one by its key: `/pause indiegala-2`. The
key is visible in the address of the site's page.

## Keys and Steam

Several Steam accounts means several bots in ArchiSteamFarm.

- **Keys from giveaways.** A profile has "This profile's Steam — ASF bot"
  («Steam этой учётки — бот в ASF»; Edit in the profile header). Keys won by
  its sites are activated by ASF in that bot, that is, in this profile's
  Steam. Empty means the bot from the farm settings.
- **Free Steam games** is one card for all profiles, in Main: ASF adds the
  game to every bot. The "ASF bots" («Боты ASF») field in its settings narrows
  the list: names separated by commas; empty means all bots.

## Removing

- **A site from a profile**: on the site's page, the Connection (Подключение)
  tab → "Remove from profile" («Убрать из учётки»). Other profiles are not
  affected.
- **A whole profile**: "Delete profile" («Удалить учётку») in its header. The
  farm stops all of its sites, forgets their cookies and removes the cards.
  Main cannot be deleted.

The number of a deleted card is never given to a new one, so histories do not
get mixed up.

## Where it is stored

Profiles are stored in `farm.json` (the `profiles` section), and their sites
under numbered keys: `indiegala-2`, `steamgifts-3` (the `accounts` section;
the site itself has a `profile` field). SteamGifts keeps its settings in
`config.ini`, so its cards in other profiles have their own file:
`accounts/steamgifts-2/config.ini`. The `STEAMGIFTBOT_*` environment variables
apply to Main only. See [Files and data](Files-and-Data-EN.md) for more.
