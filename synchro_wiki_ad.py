#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import re
import sys
from ldap3 import Connection, Server, SUBTREE
import pymysql.cursors

def get_users_ad(server, user, password):
    """
    Get users'names and user's groups to AD.

    Args:
        param1 (str): the AD's server.
        param2 (str): the user's name to connect to AD.
        param3 (str): the user's password.

    Returns:
        The list of users and the list of concat user:group.
                                                ex : Toto.nom:Acces_Wiki_admin
    """
    server1 = Server(server)
    try:
        conn = Connection(server1, user, password, auto_bind=True)
        conn.start_tls()
        conn.search(search_base='OU=ACCES,OU=GROUPES,DC=domain,DC=com',
                    search_filter='(&(objectclass=group)(memberOf=CN=Acces_wiki,OU=ACCES,OU=GROUPES,DC=domain,DC=com))', search_scope=SUBTREE, attributes=['sAMAccountName', 'member'])
    except Exception:
        print('ERROR: %s' % sys.exc_info()[1])
    list_ad = []
    list_ad_user = []
    for group in conn.entries:
        for people in group.member:
            match = re.match(r'^CN=(?P<cn>.*?),OU=.*', people)
            c_name = match.group('cn')
            conn.search(search_base='OU=USERS,DC=domain,DC=com',
                        search_filter='(&(objectclass=person)(CN=%s))' % c_name,
                        search_scope=SUBTREE, attributes=['sAMAccountName'])
            for people in conn.entries:
                try:
                    list_ad.append('%s%s'%(str(people['sAMAccountName'])[0].upper(), str(people['sAMAccountName'])[1:].lower())+':'+(str(group['sAMAccountName'])))
                    list_ad_user.append('%s%s'%(str(people['sAMAccountName'])[0].upper(), str(people['sAMAccountName'])[1:].lower()))
                except Exception:
                    print('ERROR: %s' % sys.exc_info()[1])
    return (list_ad, list_ad_user)


class WikiDb(object):
    """
       Create the object to alter the Wiki base by synchronizing this base and AD's base.
    """
    def __init__(self, host, user, password, db):
        """Construct to object :

        Args:
            param1 (str): Wiki base server's name or his IP
            param2 (str): Wiki's user
            param3 (str): user's password
            param4 (str): Wiki database's name
        """
        self.connexion = pymysql.connect(host=host, user=user, password=password, db=db, autocommit=True)
        self.cursor = self.connexion.cursor()

    def users_list(self):
        """
        Get all user from Wiki base except the user with id 1, he's the wikiuser.

        Returns:
            All user in a list.
        """
        request_select_user = """SELECT user_name FROM user WHERE user_id > 1"""
        self.cursor.execute(request_select_user)
        return self.cursor.fetchall()

    def users_groups_list(self):
        """
        Get all concat user/user's group from Wikibase.

        Returns:
            The couple user/group in a list.
        """
        request_select_user_group = """SELECT CONCAT(user_name,':', ug_group)
                                                    FROM user AS u, user_groups AS g
                                                    WHERE u.user_id = g.ug_user"""
        self.cursor.execute(request_select_user_group)
        return self.cursor.fetchall()

    def insert_group(self, ug_user, ug_group):
        """
        Insert the user'group if it is outdated with the user_id in the database and the group'name associate to the user'name in the AD.

        Args:
            param1 (str): the user_name in the AD.
            param2 (str): the the user's group name in the AD.
        """
        request_insert_group = """INSERT INTO user_groups (ug_user, ug_group)
                                                           VALUES ((SELECT user_id FROM user
                                                                    WHERE user_name = '{0}'), '{1}')"""
        query = request_insert_group.format(ug_user, ug_group)
        self.cursor.execute(query)

    def delete_user(self, user_name):
        """
        Delete the user int he databse if it is outdated compared in the AD.

        Args:
            param1 (str): the user's name in the wiki base.
        """
        request_delete_user = """DELETE FROM user WHERE user_name = '{0}' AND user_id > 1"""
        query = request_delete_user.format(user_name)
        self.cursor.execute(query)

    def delete_group(self, ug_user, ug_group):
        """
        Delete the group and the user'id in the wikibase if it is outdated copared in the AD.

        Args:
            param1 (str): user's name to wikibase.
            param2 (str): usergroup's name to wikibase.
        """
        request_delete_group = """DELETE FROM user_groups WHERE ug_user = (
                                                                           SELECT user_id
                                                                           FROM user
                                                                           WHERE user_name = '{0}')
                                                          AND ug_group = '{1}' 
                                                                           AND ug_user > 1 """
        query = request_delete_group.format(ug_user, ug_group)
        self.cursor.execute(query)

    def close(self):
        """
        Close the connection to the Wikibase.
        """
        self.connexion.close()

def update_db_wiki(dbwiki, list_ad, list_ad_user):
    """
    Treatments allows the update of the database.

    Args:
        param1 (object): the object for the connexion and action in the base.
        param2 (list): the list of all couple user/group in AD.
        param3 (list): the list of all user in AD.
    """
    list_ad_user = list(set(list_ad_user))
    list_ad_user.sort()
    list_db_user = dbwiki.users_list()
    list_db_group = dbwiki.users_groups_list()
    for index_ad in list_ad_user:
        if (index_ad,) not in list_db_user:
            try:
                dbwiki.insert_user(index_ad)
            except Exception:
                print('ERROR add_user: %s' % sys.exc_info()[1])
    for index_db in list_db_user:
        if index_db[0] not in list_ad_user:
            try:
                dbwiki.delete_user(index_db[0])
            except Exception:
                print('ERROR delete_user: %s' % sys.exc_info()[1])
    for index_ad in list_ad:
        if (index_ad.encode("Utf-8"),) not in list_db_group:
            try:
                dbwiki.insert_group((index_ad.split(':')[0]), (index_ad.split(':')[1]))
            except Exception:
                print('ERROR update_group: %s' % sys.exc_info()[1])
    for index_db in list_db_group:
        if index_db[0].decode() not in list_ad:
            try:
                dbwiki.delete_group(((index_db[0].decode()).split(':')[0]), ((index_db[0].decode()).split(':')[1]))
            except Exception:
                print('ERROR delete_group: %s' % sys.exc_info()[1])


def run():
    """
    Launch in the order of functions and methods. And instantiated to object.
    """
    list_ad, list_ad_user = get_users_ad('hostAD.domain.com', 'CN=user_ad,OU=USERS,DC=domain,DC=com', 'password')
    db = WikiDb('host', 'user_db', 'password', 'wikidb')
    update_db_wiki(db, list_ad, list_ad_user)
    db.close()


if __name__ == '__main__':
    """
        Run the script.
    """
    run()
