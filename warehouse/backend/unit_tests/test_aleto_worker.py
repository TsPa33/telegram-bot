from contextlib import closing

from app.aleto_worker import database, process_one, select_catalogue

from app.services.aleto_adapter import fixture


def test_committed_page_is_not_fetched_again_after_reopen(tmp_path):
    manifest, _ = fixture('XC60')
    pages = {page['url']: page['html'].encode() for page in manifest['pages']}
    root = manifest['pages'][0]['url']

    class Source:
        requested = []

        def read(self, url, **kwargs):
            self.requested.append(url)
            return pages[url]

    source = Source()
    path = tmp_path / 'worker.sqlite3'
    with closing(database(path)) as db, db:
        job_id = db.execute(
            "INSERT INTO parser_jobs(manufacturer, model, generation) VALUES ('Volvo', 'XC60', '')",
        ).lastrowid
        select_catalogue(db, job_id, root)
        db.commit()
        assert process_one(db, source)
    with closing(database(path)) as db, db:
        db.execute("UPDATE parser_jobs SET status='paused' WHERE id=?", (job_id,))
        assert not process_one(db, source)
        db.execute("UPDATE parser_jobs SET status='queued' WHERE id=?", (job_id,))
        db.commit()
        assert process_one(db, source)
        db.commit()
        assert process_one(db, source)
        assert db.execute('SELECT status FROM parser_jobs WHERE id=?', (job_id,)).fetchone()[0] == 'completed'
        assert db.execute('SELECT COUNT(DISTINCT article) FROM market_observations').fetchone()[0] == 2
    assert source.requested == list(pages)
