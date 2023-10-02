import requests
import pickle

from functools import partial
from resources.lib.ui import database, utils, control#, get_meta
from resources.lib import indexers
from resources import jz
from resources.lib.indexers.syncurl import SyncUrl

class SIMKLAPI:
    def __init__(self):
        # self.ClientID = "5178a709b7942f1f5077b737b752eea0f6dee684d0e044fa5acee8822a0cbe9b" # Swag API Key
        # self.ClientID = "503b6b37476926a7a17ac86b95a81b245879955a7531e3e7d8913c0624796ea0" # My API key
        
        self.ClientID = "59dfdc579d244e1edf6f89874d521d37a69a95a1abd349910cb056a1872ba2c8" # Otaku API key
        self.baseUrl = "https://api.simkl.com"
        self.imagePath = "https://wsrv.nl/?url=https://simkl.in/episodes/%s_w.webp"


    def parse_episode_view(self, res, anilist_id, season, poster, fanart, eps_watched, update_time, tvshowtitle, dub_data, filler_data, filler_enable, title_disable):

        url = "%s/%s/" % (anilist_id, res['episode'])

        title = res.get('title')
        if not title:
            title = f'Episode {res["episode"]}'

        image = self.imagePath % res['img'] if res.get('img') else poster

        info = {
            'plot': res.get('description', ''),
            'title': title,
            'season': season,
            'episode': int(res["episode"]),
            'tvshowtitle': tvshowtitle,
            'mediatype': 'episode'
        }
        if eps_watched:
            if int(eps_watched) >= res['episode']:
                info['playcount'] = 1

        try:
            info['aired'] = res['date'][:10]
        except KeyError:
            pass

        try:
            filler = filler_data[res['episode'] - 1]
        except IndexError:
            filler = ''
        code = jz.get_second_label(info, dub_data)
        if not code and filler_enable:
            filler = code = control.colorString(filler, color="red") if filler == 'Filler' else filler
        info['code'] = code

        parsed = utils.allocate_item(title, "play/%s" % url, False, image, info, fanart, poster)
        database.update_episode(anilist_id, season=season, number=res['episode'], update_time=update_time, kodi_meta=parsed, filler=filler)

        if title_disable and info.get('playcount') != 1:
            parsed['info']['title'] = f'Episode {res["number"]}'
            parsed['info']['plot'] = None
        return parsed

    def process_episode_view(self, anilist_id, poster, fanart, eps_watched, tvshowtitle, dub_data, filler_data, filler_enable, title_disable):
        from datetime import date
        update_time = date.today().isoformat()

        result = self.get_anime_info(anilist_id)
        if not result:
            return []
        season = result.get('season')
        # if not season:
        #     all_titles = [title['name'] for title in result['alt_titles']]
        #     if result['en_title']:
        #         all_titles.append(result['en_title'])
        #     s_id = utils.get_season(all_titles)
        #     season = s_id[0] if s_id else 1
        if not season:
            sync_data = SyncUrl().get_anime_data(anilist_id, 'Anilist')
            s_id = utils.get_season(sync_data[0])
            season = s_id[0] if s_id else 1

        season = int(season)
        database.update_season(anilist_id, season)

        result_ep = self.get_episode_meta(anilist_id)
        episodes = [x for x in result_ep if x['type'] == 'episode']

        # get_meta.collect_meta(anilist_id, result)

        mapfunc = partial(self.parse_episode_view, anilist_id=anilist_id, season=season,
                          poster=poster, fanart=fanart, eps_watched=eps_watched, update_time=update_time,
                          tvshowtitle=tvshowtitle, dub_data=dub_data, filler_data=filler_data, filler_enable=filler_enable,
                          title_disable=title_disable)

        all_results = list(map(mapfunc, episodes))
        if len(all_results) == 0 or control.getSetting('interface.showunairedeps') == 'true':
            total_ep = result.get('total_episodes', 0)
            empty_ep = []
            for ep in range(len(all_results) + 1, total_ep + 1):
                empty_ep.append({
                    'id': f'{tvshowtitle}-season-{season}-episode-{ep}',
                    # 'title': control.colorString(f'Episode {ep}', 'red'),
                    'title': f'Episode {ep}',
                    'episode': ep,
                    'image': poster
                })
            mapfunc_emp = partial(self.parse_episode_view, anilist_id=anilist_id, season=season, poster=poster, fanart=fanart,
                                eps_watched=eps_watched, update_time=update_time, tvshowtitle=tvshowtitle, dub_data=dub_data,
                                filler_data=filler_data, filler_enable=filler_enable, title_disable=title_disable)
            all_results += list(map(mapfunc_emp, empty_ep))

        control.notify("SIMKL", f'{tvshowtitle} Added to Database', icon=poster)
        return all_results


    def append_episodes(self, anilist_id, episodes, eps_watched, poster, fanart, tvshowtitle, filler_data=None,
                        dub_data=None, filler_enable=False, title_disable=False):
        import datetime
        import time
        update_time = datetime.date.today().isoformat()
        last_updated = datetime.datetime(*(time.strptime(episodes[0]['last_updated'], "%Y-%m-%d")[0:6]))
        # last_updated = datetime.datetime.strptime(episodes[0].get('last_updated'), "%Y-%m-%d") #todo add when python 11 is added

        diff = (datetime.datetime.today() - last_updated).days
        result = self.get_episode_meta(anilist_id) if diff > 3 else []

        if len(result) > len(episodes):
            season = database.get_season_list(anilist_id)['season']
            mapfunc2 = partial(self.parse_episode_view, anilist_id=anilist_id, season=season, poster=poster, fanart=fanart,
                               eps_watched=eps_watched, update_time=update_time, tvshowtitle=tvshowtitle, dub_data=dub_data,
                               filler_data=filler_data, filler_enable=filler_enable, title_disable=title_disable)
            all_results = list(map(mapfunc2, result))
            try:
                all_results = sorted(all_results, key=lambda x: x['info']['episode'])
            except TypeError:
                for inx, i in enumerate(all_results):
                    if i['url'] == "":
                        all_results.pop(inx)
                all_results = sorted(all_results, key=lambda x: x['info']['episode'])
            control.notify("SIMKL", f'{tvshowtitle} Appended to Database', icon=poster)
        else:
            mapfunc1 = partial(indexers.parse_episodes, eps_watched=eps_watched, dub_data=dub_data, filler_enable=filler_enable, title_disable=title_disable)
            all_results = list(map(mapfunc1, episodes))
        return all_results

    def get_episodes(self, anilist_id, show_meta):
        kodi_meta = pickle.loads(database.get_show(anilist_id)['kodi_meta'])

        kodi_meta.update(pickle.loads(show_meta['art']))
        fanart = kodi_meta.get('fanart')
        poster = kodi_meta.get('poster')
        eps_watched = kodi_meta.get('eps_watched')
        episodes = database.get_episode_list(anilist_id)
        tvshowtitle = kodi_meta['title_userPreferred']

        dub_data = None
        if control.getSetting('jz.dub') == 'true':
            from resources.jz.TeamUp import teamup
            dub_data = teamup.get_dub_data(kodi_meta['ename'])

        # if control.getSetting('jz.sub') == 'true':
        #     from resources.jz import AniList
        #     ani_data = AniList.get_anime_info_anilist_id(anilist_id)

        filler_enable = control.getSetting('jz.filler') == 'true'
        title_disable = control.getSetting('interface.cleantitles') == 'true'
        if episodes:
            if kodi_meta['status'] != "FINISHED":
                from resources.jz import anime_filler
                filler_data = anime_filler.get_data(kodi_meta['ename'])
                return self.append_episodes(anilist_id, episodes, eps_watched, poster, fanart, tvshowtitle, filler_data,
                                            dub_data, filler_enable, title_disable), 'episodes'
            return indexers.process_episodes(episodes, eps_watched, dub_data=dub_data, filler_enable=filler_enable,
                    title_disable=title_disable), 'episodes'

        from resources.jz import anime_filler
        filler_data = anime_filler.get_data(kodi_meta['ename'])
        return self.process_episode_view(anilist_id, poster, fanart, eps_watched, tvshowtitle=tvshowtitle, dub_data=dub_data,
                filler_data=filler_data, filler_enable=filler_enable, title_disable=title_disable), 'episodes'

    def get_anime_info(self, anilist_id):
        show_ids = database.get_show(anilist_id)
        simkl_id = show_ids['simkl_id']
        if not simkl_id:
            simkl_id = self.get_simkl_id('anilist', anilist_id)
            database.add_mapping_id(anilist_id, 'simkl_id', simkl_id)

        params = {
            'extended': 'full',
            'client_id': self.ClientID
        }
        r = requests.get(f'{self.baseUrl}/anime/{simkl_id}', params=params)
        res = r.json() if r.ok else {}
        return res

    def get_episode_meta(self, anilist_id):
        show_ids = database.get_show(anilist_id)
        simkl_id = show_ids['simkl_id']
        if not simkl_id:
            mal_id = show_ids['mal_id']
            simkl_id = self.get_simkl_id('mal', mal_id)
            database.add_mapping_id(anilist_id, 'simkl_id', simkl_id)
        params = {
            'extended': 'full',
        }
        r = requests.get(f'{self.baseUrl}/anime/episodes/{simkl_id}', params=params)
        res = r.json()
        return res

    def get_simkl_id(self, send_id, anime_id):
        params = {
            send_id: anime_id,
            "client_id": self.ClientID,
        }
        r = requests.get(f'{self.baseUrl}/search/id', params=params)
        r = r.json()
        anime_id = r[0]['ids']['simkl']
        return anime_id

    def get_mapping_ids(self, send_id, anime_id):
        # return_id = anidb, ann, mal, offjp, wikien, wikijp, instagram, imdb, tmdb, tw, tvdbslug, anilist, animeplanet, anisearch, kitsu, livechart, traktslug
        simkl_id = self.get_simkl_id(send_id, anime_id)
        params = {
            'extended': 'full',
            'client_id': self.ClientID
        }
        r = requests.get(f'{self.baseUrl}/anime/{simkl_id}', params=params)
        if r.ok:
            r = r.json()
            return r['ids']
