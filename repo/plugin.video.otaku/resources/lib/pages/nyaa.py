import pickle
import re
import requests

from functools import partial
from bs4 import BeautifulSoup, SoupStrainer
from resources.lib import debrid
from resources.lib.ui import database, source_utils, control
from resources.lib.ui.BrowserBase import BrowserBase


class Sources(BrowserBase):
    _BASE_URL = 'https://nyaa.si'

    def __init__(self):
        self.media_type = None
        self.cached = []
        self.uncached = []
        self.sources = []

    def process_nyaa_episodes(self, url, params, episode_zfill, season_zfill, part=None):
        r = requests.get(url, params)
        html = r.text
        mlink = SoupStrainer('div', {'class': 'table-responsive'})
        soup = BeautifulSoup(html, "html.parser", parse_only=mlink)
        re_mag = re.compile(r'(magnet:)+[^"]*')
        re_hash = re.compile(r'btih:(.*?)(?:&|$)')
        list_ = [
            {'magnet': i.find('a', {'href': re_mag}).get('href'),
             'name': i.find_all('a', {'class': None})[1].get('title'),
             'size': i.find_all('td', {'class': 'text-center'})[1].text.replace('i', ''),
             'downloads': int(i.find_all('td', {'class': 'text-center'})[-1].text),
             'seeders': int(i.find_all('td', {'class': 'text-center'})[-3].text),
             'hash': re_hash.findall(i.find('a', {'href': re_mag}).get('href'))[0]
             } for i in soup.select("tr.danger,tr.default,tr.success")
        ]

        if self.media_type != 'movie':
            filtered_list = source_utils.filter_sources(list_, int(season_zfill), int(episode_zfill), part=part)
        else:
            filtered_list = list_
        cache_list, uncashed_list_ = debrid.torrentCacheCheck(filtered_list)
        cache_list = sorted(cache_list, key=lambda k: k['downloads'], reverse=True)

        uncashed_list = [i for i in uncashed_list_ if i['seeders'] > 0]
        uncashed_list = sorted(uncashed_list, key=lambda k: k['seeders'], reverse=True)
        mapfunc = partial(self.parse_nyaa_view, episode=episode_zfill)
        all_results = list(map(mapfunc, cache_list))
        if control.settingids.showuncached:
            mapfunc2 = partial(self.parse_nyaa_view, episode=episode_zfill, cached=False)
            all_results += list(map(mapfunc2, uncashed_list))
        return all_results

    def process_nyaa_movie(self, url, params):
        r = requests.get(url, params=params)
        res = r.text
        results = BeautifulSoup(res, 'html.parser')
        rex = r'(magnet:)+[^"]*'
        search_results = [
            (i.find_all('a', {'href': re.compile(rex)})[0].get('href'),
             i.find_all('a', {'class': None})[1].get('title'),
             i.find_all('td', {'class': 'text-center'})[1].text,
             i.find_all('td', {'class': 'text-center'})[-1].text,
             i.find_all('td', {'class': 'text-center'})[-3].text
             ) for i in results.select("tr.danger,tr.default,tr.success")]

        list_ = [
            {
             'magnet': magnet,
             'name': name,
             'size': size.replace('i', ''),
             'downloads': int(downloads),
             'seeders': int(seeders)
             } for magnet, name, size, downloads, seeders in search_results]

        for idx, torrent in enumerate(list_):
            torrent['hash'] = re.findall(r'btih:(.*?)(?:&|$)', torrent['magnet'])[0]

        cache_list, uncashed_list = debrid.torrentCacheCheck(list_)
        cache_list = sorted(cache_list, key=lambda k: k['downloads'], reverse=True)
        mapfunc = partial(self.parse_nyaa_view, episode=1)
        all_results = list(map(mapfunc, cache_list))
        return all_results

    def get_sources(self, query, mal_id, episode, status, media_type):
        query = self._clean_title(query).replace('-', ' ')
        self.media_type = media_type
        if media_type == 'movie':
            return self.get_movie_sources(query, mal_id)

        self.sources = self.get_episode_sources(query, mal_id, episode, status)
        if not self.sources and ':' in query:
            q1, q2 = query.split('|', 2)
            q1 = q1[1:-1].split(':')[0]
            q2 = q2[1:-1].split(':')[0]
            query2 = '({0})|({1})'.format(q1, q2)
            self.sources = self.get_episode_sources(query2, mal_id, episode, status)

        # remove any duplicate sources
        self.append_cache_uncached_noduplicates()
        return {'cached': self.cached, 'uncached': self.uncached}

    def get_episode_sources(self, show, mal_id, episode, status):
        nyaa_sources = []
        if 'part' in show.lower():
            part = re.search(r'part ?(\d+)', show.lower())
            if part:
                part = int(part.group(1).strip())
        else:
            part = None

        season = database.get_episode(mal_id)['season']
        season_zfill = str(season).zfill(2)
        episode_zfill = episode.zfill(2)
        query = f'{show} "- {episode_zfill}"'
        query += f'|"S{season_zfill}E{episode_zfill}"'

        params = {
            'f': '0',
            'c': '1_0',
            'q': query.replace(' ', '+'),
            's': 'downloads',
            'o': 'desc'
        }
        nyaa_sources += self.process_nyaa_episodes(self._BASE_URL, params, episode_zfill, season_zfill, part)
        if status == "Finished Airing":
            query = '%s "Batch"|"Complete Series"' % show
            episodes = pickle.loads(database.get_show(mal_id)['kodi_meta'])['episodes']
            if episodes:
                query += f'|"01-{episode_zfill}"|"01~{episode_zfill}"|"01 - {episode_zfill}"|"01 ~ {episode_zfill}"'

            if season_zfill:
                query += f'|"S{season_zfill}"|"Season {season_zfill}"'
                query += f'|"S{season_zfill}E{episode_zfill}"'

            query += f'|"- {episode_zfill}"'
            params = {
                'f': '0',
                'c': '1_0',
                'q': query.replace(' ', '+'),
                's': 'seeders',
                'o': 'desc'
            }
            nyaa_sources += self.process_nyaa_episodes(self._BASE_URL, params, episode_zfill, season_zfill, part)

        params = {
            'f': '0',
            'c': '1_0',
            'q': query.replace(' ', '+')
        }
        nyaa_sources += self.process_nyaa_episodes(self._BASE_URL, params, episode_zfill, season_zfill, part)

        show = show.lower()
        if 'season' in show:
            query1, query2 = show.rsplit('|', 2)
            match_1 = re.match(r'.+?(?=season)', query1)
            if match_1:
                match_1 = match_1.group(0).strip() + ')'
            match_2 = re.match(r'.+?(?=season)', query2)
            if match_2:
                match_2 = match_2.group(0).strip() + ')'
            query = f'{match_1}|{match_2}'
        params = {
            'f': '0',
            'c': '1_0',
            'q': query.replace(' ', '+')
        }
        nyaa_sources += self.process_nyaa_episodes(self._BASE_URL, params, episode_zfill, season_zfill, part)
        return nyaa_sources

    def get_movie_sources(self, query, mal_id):
        params = {
            'f': '0',
            'c': '1_2',
            'q': query.replace(' ', '+'),
            's': 'downloads',
            'o': 'desc'
        }

        self.sources = self.process_nyaa_movie(self._BASE_URL, params)

        # make sure no duplicate sources
        self.append_cache_uncached_noduplicates()
        return {'cached': self.cached, 'uncached': self.uncached}

    @staticmethod
    def parse_nyaa_view(res, episode, cached=True):
        source = {
            'release_title': res['name'],
            'hash': res['hash'],
            'type': 'torrent',
            'quality': source_utils.getQuality(res['name']),
            'debrid_provider': res.get('debrid_provider'),
            'provider': 'nyaa',
            'episode_re': episode,
            'size': res['size'],
            'byte_size': 0,
            'info': source_utils.getInfo(res['name']),
            'lang': source_utils.getAudio_lang(res['name']),
            'cached': cached,
            'seeders': res['seeders']
        }
        match = re.match(r'(\d+).(\d+) (\w+)', res['size'])
        if match:
            source['byte_size'] = source_utils.convert_to_bytes(float(f'{match.group(1)}.{match.group(2)}'), match.group(3))
        if not cached:
            source['magnet'] = res['magnet']
            source['type'] += ' (uncached)'
        return source

    def append_cache_uncached_noduplicates(self):
        seen_sources = []
        for source in self.sources:
            if source not in seen_sources:
                seen_sources.append(source)
                if source['cached']:
                    self.cached.append(source)
                else:
                    self.uncached.append(source)