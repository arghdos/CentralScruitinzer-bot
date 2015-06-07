# DataBase.py -- contains wrapper for a SQL database

import sqlite3
import logging
import datetime
import re
import Blacklist


class DataBaseWrapper(object):
    def __init__(self, databasefile, create_on_enter=True):
        self.databasefile = databasefile
        self.create_on_enter = create_on_enter

    """A wrapper to the SQL Database, designed be used in conjunction with a 'with'"""

    def __enter__(self):
        class DataBase:
            """
            :type db: sqlite3.Connection
            :type cursor: sqlite3.Cursor
            """

            def __init__(self, databasefile, create_on_enter):
                # open the database and create cursor
                try:
                    self.db = sqlite3.connect(databasefile, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
                    self.cursor = self.db.cursor()
                    if create_on_enter:
                        self.__create_table()
                    self.db.create_function("regexp", 2, self.regexp)
                    self.db.create_function("domain_eq", 2, self.domain_eq)
                except sqlite3.Error, e:
                    logging.debug(str(e))
                    logging.critical("Cannot open database file " + databasefile)
                    raise e

            def __create_table(self):
                """Creates the post table if it does not exist already"""
                try:
                    self.cursor.execute('''create table if not exists channel_record
                    (channel_id text,
                    domain text,
                    blacklist integer default 0,
                    strike_count integer default 0,
                    listed_by text,
                    list_time timestamp default current_timestamp,
                    reason text,
                    primary key(channel_id, domain))''')
                    try:
                        self.cursor.execute('create index blist on channel_record(blacklist)')
                    except sqlite3.OperationalError, e:
                        if str(e) == "index blist already exists":
                            pass
                        else:
                            logging.critical("Could not create index blist on table channel_record")
                            logging.debug(str(e))
                    self.db.commit()
                except sqlite3.Error, e:
                    logging.critical("Could not create table channel_record")
                    logging.debug(str(e))
                    return False

                try:
                    self.cursor.execute('''create table if not exists reddit_record
                    (short_url text primary key,
                    channel_id text,
                    domain text,
                    processed integer default 0,
                    date_added timestamp default current_timestamp
                    submitter text,
                    exception integer default 0)''')
                    try:
                        self.cursor.execute('create index channel on reddit_record(channel_id, domain)')
                    except sqlite3.OperationalError, e:
                        if str(e) == "index channel already exists":
                            pass
                        else:
                            logging.critical("Could not create index channel on table reddit_record")
                            logging.debug(str(e))
                    try:
                        self.cursor.execute('create index mydate on reddit_record(date_added)')
                    except sqlite3.OperationalError, e:
                        if str(e) == "index mydate already exists":
                            pass
                        else:
                            logging.critical("Could not create index mydate on table reddit_record")
                            logging.debug(str(e))

                    try:
                        self.cursor.execute('create index submit on reddit_record(submitter)')
                    except sqlite3.OperationalError, e:
                        if str(e) == "index submit already exists":
                            pass
                        else:
                            logging.critical("Could not create index submit on table reddit_record")
                            logging.debug(str(e))

                    try:
                        self.cursor.execute('create index baddelete on reddit_record(processed, exception)')
                    except sqlite3.OperationalError, e:
                        if str(e) == "index submit already exists":
                            pass
                        else:
                            logging.critical("Could not create index baddelete on table reddit_record")
                            logging.debug(str(e))

                    self.db.commit()
                except sqlite3.Error, e:
                    logging.debug(str(e))
                    logging.critical("Could not create table reddit_record")
                    return False
                return True

            def newest_reddit_entries(self, limit=1):
                """
                Returns a list containing the timestamp of creation of the latest (limit) posts
                :param limit:
                :return:
                """
                try:
                    return [x[0] for x in self.cursor.execute("select date_added from reddit_record order by date_added desc limit ?",
                                                (limit,)).fetchall()]
                except Exception, e:
                    logging.error("Could not select newest reddit entries")
                    logging.debug(str(e))

            def check_channel_empty(self):
                """Checks wheter the reddit_record is empty or not"""
                try:
                    self.cursor.execute("select count(*) from channel_record")
                    list = self.cursor.fetchone()
                    return list is None or list[0] == 0
                except Exception, e:
                    logging.error("Could not check if channel_record was empty")
                    logging.debug(str(e))

            def check_reddit_empty(self):
                """Checks wheter the reddit_record is empty or not"""
                try:
                    self.cursor.execute("select count(*) from reddit_record")
                    list = self.cursor.fetchone()
                    return list is None or list[0] == 0
                except Exception, e:
                    logging.error("Could not check if reddit_record was empty")
                    logging.debug(str(e))

            def regexp(self, expr, item):
                reg = re.compile(expr)
                return reg.search(item) is not None

            def domain_eq(self, domain, item):
                return domain == item or domain.startswith(item)

            def add_reddit(self, reddit_entries):
                """adds the supplied reddit entries to the reddit_record

                :param reddit_entries: a list of tuples consisting of (short_url, channel_id, domain, date_added, submitter)
                :return:
                """
                try:
                    if not isinstance(reddit_entries, list):
                        reddit_entries = list(reddit_entries)
                    reddit_entries = [(e,) if not isinstance(e, tuple) else e for e in reddit_entries]
                    self.cursor.executemany(
                        '''insert or ignore into reddit_record (short_url, channel_id, domain, date_added, submitter) values(?, ?, ?, ?, ?)''',
                        reddit_entries)
                    self.db.commit()
                except sqlite3.Error, e:
                    logging.error("Could not add reddit entries to database")
                    logging.debug(str(e))

            def get_reddit(self, channel_id=None, domain=None, date_added=None, processed=None, submitter=None,
                           exception=None, return_channel_id=True, return_domain=True, return_dateadded=False,
                           return_submitter=False, return_exception=False):
                """returns a list of reddit entries matching the provided search modifiers (i.e. channel_id, domain, date_added)

                :returns: a list of tuples of the form (short_url, channel_id*, domain*, date_added*, submitter* (*if specified))
                """
                query = 'select short_url'
                arglist = []
                if return_channel_id:
                    query += ', channel_id'
                if return_domain:
                    query += ', domain'
                if return_dateadded:
                    query += ', date_added'
                if return_submitter:
                    query += ', submitter'
                if return_exception:
                    query += ', exception'
                query += ' from reddit_record where '
                if channel_id is not None:
                    query += 'channel_id = ?'
                    arglist.append(channel_id)
                if domain is not None:
                    if len(arglist):
                        query += ' and '
                    query += 'domain_eq(domain, ?)'
                    arglist.append(domain)
                if date_added is not None:
                    if len(arglist):
                        query += ' and '
                    query += ' date_added > ?'
                    arglist.append(date_added)
                if processed is not None:
                    if len(arglist):
                        query += ' and '
                    query += ' processed == ?'
                    arglist.append(processed)
                if submitter is not None:
                    if len(arglist):
                        query += ' and '
                    query += ' submitter == ?'
                    arglist.append(submitter)
                if exception is not None:
                    if len(arglist):
                        query += ' and '
                    query += ' exception == ?'
                    arglist.append(exception)
                if not len(arglist):
                    return None
                try:
                    self.cursor.execute(query, tuple(arglist))
                    return self.cursor.fetchall()
                except sqlite3.Error, e:
                    logging.error("Error fetching entries from reddit_record")
                    logging.debug(str(e))

            def processed_older_than(self, the_time):
                """returns all entries from the reddit_record processed before a certain date

                :param days: how many days ago
                """
                try:
                    self.cursor.execute(
                        "select channel_id, domain from reddit_record where date_added < ? and processed = 1",
                        (the_time,))
                    return self.cursor.fetchall()
                except sqlite3.Error, e:
                    logging.error("Could not remove processed reddit records older than " + str(the_time))
                    logging.debug(str(e))

            def remove_reddit_older_than(self, the_time):
                """removes all entries from the reddit_record older than a certain date

                :param days: how many days ago
                """
                try:
                    self.cursor.execute("delete from reddit_record where date_added < ?", (the_time,))
                    self.db.commit()
                except sqlite3.Error, e:
                    logging.error("Could not remove reddit records older than " + str(the_time))
                    logging.debug(str(e))

            def remove_reddit(self, reddit_entries):
                """removes the entries from the reddit_record

                :param reddit_entries: a list of the short_url's to delete
                """
                try:
                    if not isinstance(reddit_entries, list):
                        reddit_entries = list(reddit_entries)
                    tupled = [(entry,) if not isinstance(entry, tuple) else entry for entry in reddit_entries]
                    self.cursor.executemany('delete from reddit_record where short_url = ?', tupled)
                    self.db.commit()
                except sqlite3.Error, e:
                    logging.error("Could not remove short_url from database")
                    logging.debug(str(e))

            def max_processed_from_user(self, channel_entries):
                """Returns the maximum number of processed, non-exception posts for a single user for the given channels

                :param channel_entries: a list of tuples of (channel_id, domain)
                :return: a list of (strike count, submitter), the max # of deleted posts by the worst offending user
                """

                try:
                    if not isinstance(channel_entries, list):
                        channel_entries = list(channel_entries)
                    self.cursor.executemany('select count(short_url), submitter from reddit_record where channel_id == ?'
                                            ' and domain == ? and submitter is not null'
                                            ' and processed == 1 and exception == 0'
                                            ' group by submitter'
                                            ' order by count(short_url) desc'
                                            ' limit 1',
                                            channel_entries)
                except sqlite3.Error, e:
                    logging.error('Could not get max_processed_from_user')
                    logging.debug(str(e))


            def add_channels(self, channel_entries):
                """Adds channels to the channel_record, entries need not be unique

                :param channel_entries: a list of tuples consisting of (channel_id, domain)
                """
                try:
                    unique = []
                    for entry in channel_entries:
                        if not entry in unique:
                            unique.append(entry)
                    self.cursor.executemany('''insert into channel_record (channel_id, domain) values(?, ?)''', unique)
                    self.db.commit()
                    return True
                except sqlite3.Error, e:
                    logging.error("Could not add channels to database")
                    if __debug__:
                        logging.exception(e)
                return False

            def channel_exists(self, channel_list):
                """checks whether the specified channels exist

                :param channel_list: a list of tuples of the form (channel_id, domain)
                :return: a list of booleans indicating whether the channel exists or not
                """

                try:
                    return [self.cursor.execute("""select channel_id from channel_record where channel_id = ?
                            and domain_eq(domain, ?)""", channel).fetchone() is not None for channel in channel_list]
                except sqlite3.Error, e:
                    logging.error("Error on channel exists check")
                    logging.debug(str(e))
                    return None

            def reddit_exists(self, reddit_list):
                """checks whether the specified reddit entries exist

                :param reddit_list: a list of short_urls
                :return: a list of booleans indicating whether the reddit entry exists or not
                """
                try:
                    return [self.cursor.execute("""select short_url from reddit_record where short_url = ?""",
                                                (entry,)).fetchone() is not None for entry in reddit_list]
                except sqlite3.Error, e:
                    logging.error("Error on reddit exists check")
                    logging.debug(str(e))

            def get_channels(self, blacklist=None, blacklist_not_equal=None, domain=None, strike_count=None,
                             added_by=None, id_filter=None, return_url=False, return_blacklist=False,
                             return_strikes=False, return_added_by=False):
                """returns the channels matching the supplied query

                :param blacklist_not_equal: if set, return channels with blacklist not set to this value
                :param added_by: the mod this channel was black/whitelisted by
                :param return_url: if true, return url
                :param return_blacklist: if true, return blacklist value
                :param return_strikes: if true, return strikecount
                :param return_added_by: if true, return added_by
                :param blacklist: the black/whitelist to match
                :param domain: the domain to match
                :param strike_count: the strike count to be less than or equal to
                :param id_filter: regex filter
                :return: (channel_id, domain, channel_url (if return_url), blacklist (if return_blacklist), strike_count (if return_strikes),
                          added_by (if return_added_by))
                         or None if empty query
                """

                # setup returns
                query = "select channel_id, domain"
                if return_url:
                    query += ", channel_url"
                if return_blacklist:
                    query += ", blacklist"
                if return_strikes:
                    query += ", strike_count"
                if return_added_by:
                    query += ", added_by"
                query += " from channel_record where"

                #set up filtering criteria
                arglist = []
                if blacklist is not None:
                    if len(arglist):
                        query += " and"
                    query += " blacklist = ?"
                    arglist.append(blacklist)
                elif blacklist_not_equal is not None:
                    if len(arglist):
                        query += " and"
                    query += " blacklist != ?"
                    arglist.append(blacklist_not_equal)
                if domain is not None:
                    if len(arglist):
                        query += " and"
                    query += " domain_eq(domain, ?)"
                    arglist.append(domain)
                if strike_count is not None:
                    if len(arglist):
                        query += " and"
                    query += " strike_count >= ?"
                    arglist.append(strike_count)
                if id_filter is not None:
                    if len(arglist):
                        query += " and"
                    query += " channel_id regexp ?"
                    arglist.append(id_filter)
                if added_by is not None:
                    if len(arglist):
                        query += " and"
                    query += " added_by = ?"
                    arglist.append(added_by)
                #empty filter
                if not len(arglist):
                    return None

                #query
                try:
                    self.cursor.execute(query, tuple(arglist))
                    return self.cursor.fetchall()
                except sqlite3.Error, e:
                    logging.error("Error on get_channels fetch.")
                    logging.debug(
                        "domain, blacklist, id_filter:" + str(domain) + ", " + str(blacklist) + ", " + str(id_filter))

            def set_blacklist(self, channel_entries, value, added_by, reason=None):
                """Updates the black/whitelist for the given channel entries

                :param added_by: the user causing this blacklist set (sets field added_by)
                :param channel_entries: a list of tuples of the form (channel_id, domain)
                :param value: the new blacklist enum value
                """
                try:
                    if isinstance(reason, list) and len(reason) == len(channel_entries):
                        self.cursor.executemany('update channel_record set blacklist = ?, added_by = ?, reason = ?'
                                                ' where channel_id = ? and domain_eq(domain, ?)',
                                                [(value, added_by, reason[i], channel[i][0], channel[i][1]) for i, channel in enumerate(channel_entries)])
                    else:
                        self.cursor.executemany('update channel_record set blacklist = ?, added_by = ?, reason = ?'
                                                ' where channel_id = ? and domain_eq(domain, ?)',
                                                [(value, added_by, reason, channel[0], channel[1]) for channel in channel_entries])
                    self.db.commit()
                except sqlite3.Error, e:
                    logging.error("Error on set_blacklist.")
                    logging.debug(str(e))

            def check_blacklist(self, channel_entries, value):
                """Checks that the black/whitelist for the given channel entries are set to the requested value
                Returns a list of booleans indicating

                :param channel_list: a list of tuples of the form (channel_id, domain)
                :return: a list of booleans indicating whether the channel exists and has the specified blacklist value or not
                """
                try:
                    return [self.cursor.execute("""select channel_id from channel_record where channel_id = ?
                            and domain_eq(domain, ?) and blacklist = ?""", (channel[0], channel[1], value)).fetchone()
                            is not None for channel in channel_entries]
                except sqlite3.Error, e:
                    logging.error("Error on set_blacklist.")
                    logging.debug(str(e))

            def get_blacklist(self, channel_entries):
                """Gets the blacklist for the specified channels

                :param channel_entries: a list of tuples of the form (channel_id, domain)
                """
                try:
                    list = []
                    for channel in channel_entries:
                        list.append(self.cursor.execute('select blacklist from channel_record where '
                                                        'channel_id = ? and domain_eq(domain, ?)', channel).fetchone())
                    list = [entry[0] if entry else Blacklist.BlacklistEnums.NotFound for entry in list]
                    return list
                except sqlite3.Error, e:
                    logging.error("Error on get_blacklist.")
                    logging.debug(str(e))

            def set_strikes(self, channel_entries):
                """Updates the strike count for the given channels

                :param channel_entries: a list of tuples of the form (channel_id, domain, new_strike_count)
                """
                try:
                    reordered = [(entry[2], entry[0], entry[1]) for entry in channel_entries]
                    self.cursor.executemany('update channel_record set strike_count = ? where channel_id = ?'
                                            ' and domain_eq(domain, ?)', reordered)
                    self.db.commit()
                except sqlite3.Error, e:
                    logging.error("Error on set_strikes.")
                    logging.debug(str(e))

            def subtract_strikes(self, channel_entries):
                """Subtracts from the strike count for the given channels

                :param channel_entries: a list of tuples of the form (add_strikes, channel_id, domain)
                """
                try:
                    self.cursor.executemany('update channel_record set strike_count = strike_count - ? where \
                                             channel_id = ? and domain_eq(domain, ?)', channel_entries)
                    self.db.commit()
                except sqlite3.Error, e:
                    logging.error("Error on subtract_strikes.")
                    logging.debug(str(e))


            def add_strike(self, channel_entries):
                """Adds one to the strike count for the given channels

                :param channel_entries: a list of tuples of the form (add_strikes, channel_id, domain)
                """
                try:
                    self.cursor.executemany('update channel_record set strike_count = strike_count + ? where \
                                             channel_id = ? and domain_eq(domain, ?)', channel_entries)
                    self.db.commit()
                except sqlite3.Error, e:
                    logging.error("Error on add_strikes.")
                    logging.debug(str(e))

            def set_processed(self, post_list):
                """Sets the given channel entries processed to 1

                :param channel_entries: a list of short_urls
                """
                try:
                    tupled = [(val,) for val in post_list]
                    self.cursor.executemany('update reddit_record set processed = 1 where short_url = ?', tupled)
                    self.db.commit()
                except sqlite3.Error, e:
                    logging.error("Error on set_processed.")
                    logging.debug(str(e))

            def set_exception(self, post_list):
                """Sets the given channel entries exception to 1

                :param channel_entries: a list of short_urls
                """
                try:
                    tupled = [(val,) for val in post_list]
                    self.cursor.executemany('update reddit_record set exception = 1 where short_url = ?', tupled)
                    self.db.commit()
                except sqlite3.Error, e:
                    logging.error("Error on set_processed.")
                    logging.debug(str(e))


        self.db = DataBase(self.databasefile, self.create_on_enter)
        return self.db

    def __exit__(self, exc_type, exc_val, exc_tb):
        """ Closes the database and commits any changes"""
        try:
            self.db.db.commit()
            self.db.db.close()
        except Exception, e:
            logging.critical("Error on database close/commit")
            logging.debug(str(e))