import discord, random, argparse, os.path, itertools
import numpy as np
from discord.ext import commands as bot
from feh_alias import *
from fehwiki_parse import *

class MagikarpJump:
    """The game we don't play anymore."""

    def __init__(self, bot):
        self.bot = bot

    @bot.command(aliases=['Lmr'])
    async def lmr(self):
        """I will tell you which rod will net you the best Magikarp."""
        await self.bot.say(random.choice(['L', 'M', 'R']))

# these are constant so declare up here
stats = ['HP', 'ATK', 'SPD', 'DEF', 'RES']
merge_bonuses = [np.zeros(5), np.array([1,1,0,0,0]), np.array([1,1,1,1,0]), np.array([2,1,1,1,1]), np.array([2,2,2,1,1]), np.array([2,2,2,2,2]),
                 np.array([3,3,2,2,2]), np.array([3,3,3,3,2]), np.array([4,3,3,3,3]), np.array([4,4,4,3,3]), np.array([4,4,4,4,4])]
summoner_bonuses = {None:np.zeros(5), 'c':np.array([3,0,0,0,2]), 'b':np.array([4,0,0,2,2]), 'a':np.array([4,0,2,2,2]), 's':np.array([5,2,2,2,2])}

def get_unit_stats(args, default_rarity=None, sender=None):
    # convert to lower case
    args = list(map(lambda x:x.lower(), args))
    try:
        # get IV information
        boons = ['+'+s.lower() for s in stats]
        banes = ['-'+s.lower() for s in stats]
        boon, args = find_arg(args, boons, stats, 'boons')
        bane, args = find_arg(args, banes, stats, 'banes')
        if (boon and not bane) or (bane and not boon):
            return 'Only boon or only bane specified.'
        if boon is not None and bane is not None:
            if (boon == bane):
                return 'Boon is the same as bane.'
        # get merge number
        merges = ['+'+str(i) for i in range(1,11)]
        merge, args = find_arg(args, merges, range(1,11), 'merge levels')
        # get summoner support level
        supports = ['c', 'b', 'a', 's']
        support, args = find_arg(args, supports, supports, 'summoner support levels')
        # get rarity
        rarities = [str(i)+'*' for i in range(1,6)]
        rarity, args = find_arg(args, rarities, range(1,6), 'rarities')
        if rarity is None:
            rarity = default_rarity
        # check for manual stat modifiers as well
        modifiers = [a for a in args if '/' in a]
        if modifiers:
            for i in range(len(modifiers)):
                modifier = modifiers[i]
                args.remove(modifier)
                # check that each modifier is valid
                modifier = modifier.split('/')
                if len(modifier) > 5:
                    return 'Too many stat modifiers specified.'
                if not all([m[0] in ['-','+']+list(map(str, range(10))) and (m[1:].isdigit() or m[1:] == '') for m in modifier]):
                    return 'Stat modifiers in wrong format (-number or +number).'
                modifier_array = np.zeros(5, dtype=np.int32)
                modifier_array[:len(modifier)] = list(map(int, modifier))
                modifiers[i] = modifier_array
            modifiers = np.array(modifiers).sum(axis=0)
        else:
            modifiers = None
        args = ' '.join(args)
        unit = find_name(args, sender=sender)
        if unit == INVALID_HERO:
            return 'Could not find the hero %s. Perhaps I could not read one of your parameters properly.' % args
        # confirm its a unit
        categories = get_categories(unit)
        if categories is None:
            return 'Could not find the hero %s. Perhaps I could not read one of your parameters properly.' % unit
        if 'Heroes' not in categories:
            return '%s does not seem to be a hero.' % (unit)
        # actually fetch the unit's information
        html = get_page_html(unit)
        if html is None:
            return 'Could not find the hero %s. Perhaps I could not read one of your parameters properly.' % unit
        base_stats_table, max_stats_table = get_heroes_stats_tables(html)
        base_stats = table_to_array(base_stats_table, boon, bane, rarity)
        max_stats = table_to_array(max_stats_table, boon, bane, rarity)
        # check if empty
        if not any([any(r) for r in base_stats]):
            return 'This hero does not appear to be available at the specified rarity.'
        # calculate merge bonuses
        if merge is not None:
            for i in range(5):
                if any(base_stats[i]):
                    ordered_stats = (-base_stats[i]).argsort()
                    bonuses = np.zeros(5, dtype=np.int32)
                    bonuses[ordered_stats] = merge_bonuses[merge]
                    base_stats[i] += bonuses
                    max_stats[i] += bonuses
        # summoner bonuses
        if support is not None:
            for i in range(5):
                if any(base_stats[i]):
                    base_stats[i] += summoner_bonuses[support]
                    max_stats[i] += summoner_bonuses[support]
        # add flat modifiers
        if modifiers is not None:
            for i in range(5):
                if any(base_stats[i]):
                    base_stats[i] += modifiers
                    max_stats[i] += modifiers
        return (unit, base_stats, max_stats)
    except ValueError as err:
        return err.args[0]
    except urllib.error.HTTPError as err:
        if err.code == 500:
            return "Unfortunately, it seems like I cannot access my sources at the moment. Please try again later."


def find_arg(args, param_list, return_list, param_type, remove=True):
    """Finds arguments that exist in param_list and return the corresponding value from return_list."""
    arg_finding = [i in args for i in param_list]
    arg_index = None
    if arg_finding.count(True) > 1:
        raise ValueError('Multiple %s specified.' % param_type)
    elif arg_finding.count(True) == 1:
        arg_index = arg_finding.index(True)
    arg = return_list[arg_index] if arg_index is not None else None
    if arg is not None and remove:
        args.remove(param_list[arg_index])
    return arg, args


def table_to_array(table, boon, bane, rarity):
    #convert dictionary format to numpy arrays, accounting for boons banes and rarity
    array = np.zeros((5,5), dtype=np.int32)
    for i in range(len(table)):
        row = table[i]
        row_rarity = int(row['Rarity'])
        if rarity is not None and row_rarity != rarity:
            continue
        else:
            row_rarity -= 1
        for key in row:
            if key in ['Rarity','Total']:
                continue
            stat = row[key].split('/')
            if any([not s.isdigit() for s in stat]):
                raise ValueError('This hero does not appear to have stats yet.')
            stat_index = 1
            if boon and key == boon:
                stat_index = 2
            elif (bane and key == bane):
                stat_index = 0
            if len(stat) != 3:
                stat_index = 0
            array[row_rarity][stats.index(key)] = stat[stat_index]
    return array

def array_to_table(array):
    # convert numpy array back to dictionary format
    ret = []
    for i in range(len(array)):
        # skip empty rows
        if any(array[i]):
            p1 = {'Rarity':str(i+1)}
            p2 = {stats[j]:str(array[i][j]) for j in range(5)}
            p3 = {'Total':str(array[i].sum())}
            row = dict(p1, **p2)
            row.update(p3)
            ret.append(row)
    return ret

class FireEmblemHeroes:
    """The game that we do still play a lot."""

    def __init__(self, bot):
        self.bot = bot

    @bot.command(aliases=['gauntlet', 'Gauntlet', 'Fehgauntlet', 'FEHgauntlet', 'FEHGauntlet'])
    async def fehgauntlet(self):
        """I will tell you the current Voting Gauntlet score."""
        try:
            scores = get_gauntlet_scores()
        except urllib.error.HTTPError as err:
            if err.code == 500:
                await self.bot.say("Unfortunately, it seems like I cannot access my sources at the moment. Please try again later.")
                return
        longest = max(scores, key=lambda s: len(s[0]['Score']) + len(s[0]['Status']) + 3)
        longest = len(longest[0]['Score']) + len(longest[0]['Status']) + 3
        message = '```'
        for s in scores:
            message += """{:>{width}} vs {}
{:>{width}}    {}
""".format(s[0]['Name'], s[1]['Name'], (s[0]['Score'] + ' (' + s[0]['Status'] + ')'), ('(' + s[1]['Status'] + ') ' +  s[1]['Score']), width = longest)
        message += '```'
        await self.bot.say(message)

    @bot.command(pass_context=True, aliases=['Feh', 'FEH'])
    async def feh(self, ctx, *, arg):
        """I will provide some information on any Fire Emblem Heroes topic."""
        original_arg = arg
        passive_level = 3
        if arg[-1] in ['1','2','3']:
            passive_level = int(arg[-1])
            arg = arg[:-1].strip()
        try:
            arg = find_name(arg, sender = str(ctx.message.author))
        except urllib.error.HTTPError as err:
            if err.code == 500:
                await self.bot.say("Unfortunately, it seems like I cannot access my sources at the moment. Please try again later.")
                return
        if arg == INVALID_HERO:
            if original_arg.lower() in ['son', 'my son', 'waifu', 'my waifu']:
                await self.bot.say("I was not aware you had one. If you want me to associate you with one, please contact monkeybard.")
            else:
                await self.bot.say("I'm afraid I couldn't find information on %s." % original_arg)
            return
        print(arg)
        try:
            categories = get_categories(arg)
            if categories is None:
                await self.bot.say("I'm afraid I couldn't find information on %s." % arg)
                return

        except urllib.error.HTTPError as err:
            if err.code == 500:
                await self.bot.say("Unfortunately, it seems like I cannot access my sources at the moment. Please try again later.")
                return

        weapon_colours = {'Red':0xCC2844, 'Blue':0x2A63E6, 'Green':0x139F13, 'Colourless':0x54676E}

        if 'Heroes' in categories:
            html = get_page_html(arg)
            if html is None:
                await self.bot.say("I'm afraid I couldn't find information on %s." % arg)
                return
            stats = get_infobox(html)
            base_stats_table, max_stats_table = get_heroes_stats_tables(html)
            colour = weapon_colours['Colourless']
            if 'Red' in stats['Weapon Type']:
                colour = weapon_colours['Red']
            if 'Blue' in stats['Weapon Type']:
                colour = weapon_colours['Blue']
            if 'Green' in stats['Weapon Type']:
                colour = weapon_colours['Green']
            message = discord.Embed(
                title=arg,
                url=feh_source % (urllib.parse.quote(arg)),
                color=colour
            )
            icon = get_icon(arg, "Icon_Portrait_")
            if not icon is None:
                message.set_thumbnail(url=icon)
            rarity = '-'.join(a+'★' for a in stats['Rarities'] if a.isdigit())
            message.add_field(
                name="Rarities",
                value= rarity if rarity else 'N/A'
            )
            bst = get_bst(max_stats_table)
            if not bst is None:
                message.add_field(
                    name="BST",
                    value=str(bst)
                )
            message.add_field(
                name="Weapon Type",
                value=stats['Weapon Type']
            )
            message.add_field(
                name="Move Type",
                value=stats['Move Type']
            )
            message.add_field(
                name="Base Stats",
                value=format_stats_table(base_stats_table),
                inline=True
            )
            message.add_field(
                name="Max Level Stats",
                value=format_stats_table(max_stats_table),
                inline=True
            )
            skill_tables = html.find_all("table", attrs={"class":"skills-table"})
            skills = ''
            for table in skill_tables:
                headings = [a.get_text().strip() for a in table.find_all("th")]
                if 'Might' in headings:
                    # weapons
                    skills += '**Weapons:** '
                elif 'Range' in headings:
                    # assists
                    skills += '**Assists:** '
                elif 'Cooldown' in headings:
                    # specials
                    skills += '**Specials:** '
                last_learned = None
                for row in table.find_all("tr")[(-2 if 'Might' in headings else None):]:
                    slot = row.find("td", attrs={"rowspan":True}) # only passives have a rowspan data column
                    if not slot is None:
                        skills = skills.rstrip(', ')
                        if not last_learned is None:
                            skills += last_learned
                        skills += '\n**' + slot.get_text() + '**: '
                    skills += row.find("td").get_text().strip()
                    if 'Type': # if we're in passives, get learned levels
                         last_learned = ' (%s★)' % row.find_all("td")[-2 if not slot is None else -1].get_text().strip()
                    skills += ', '
                skills = skills.rstrip(', ') + last_learned + '\n'
            message.add_field(
                name="Learnable Skills",
                value=skills,
                inline=False
            )
        elif 'Weapons' in categories:
            colour = 0x222222 # for dragonstones, which are any colour
            if any(i in ['Swords', 'Red Tomes'] for i in categories):
                colour = weapon_colours['Red']
            elif any(i in ['Lances', 'Blue Tomes'] for i in categories):
                colour = weapon_colours['Blue']
            elif any(i in ['Axes', 'Green Tomes'] for i in categories):
                colour = weapon_colours['Green']
            elif any(i in ['Staves', 'Daggers', 'Bows'] for i in categories):
                colour = weapon_colours['Colourless']

            message = discord.Embed(
                title=arg,
                url=feh_source % (urllib.parse.quote(arg)),
                color=colour
            )
            icon = get_icon(arg, "Weapon_")
            if not icon is None:
                message.set_thumbnail(url=icon)
            html = get_page_html(arg)
            if html is None:
                await self.bot.say("I'm afraid I couldn't find information on %s." % arg)
                return
            stats = get_infobox(html)
            message.add_field(
                name="Might",
                value=stats['Might']
            )
            message.add_field(
                name="Range",
                value=stats['Range']
            )
            message.add_field(
                name="SP Cost",
                value=stats['SP Cost']
            )
            message.add_field(
                name="Exclusive?",
                value=stats['Exclusive?']
            )
            if 'Special Effect' in stats:
                message.add_field(
                    name="Special Effect",
                    value=stats[None],
                    inline=False
                )
            learners_table = html.find("table", attrs={"class":"sortable"})
            learners = [a.find("td").find_all("a")[1].get_text() for a in learners_table.find_all("tr")]
            if learners:
                message.add_field(
                    name="Heroes with " + arg,
                    value=', '.join(learners),
                    inline=False
                )
        elif 'Passives' in categories or 'Specials' in categories or 'Assists' in categories:
            html = get_page_html(arg)
            if html is None:
                await self.bot.say("I'm afraid I couldn't find information on %s." % arg)
                return
            stats_table = html.find("table", attrs={"class": "sortable"})
            # get the data from the appropriate row dictated by passive_level (if it exists)
            # append the inherit restriction (and slot)
            stats = [a.get_text().strip() for a in stats_table.find_all("tr")[-1 if len(stats_table.find_all("tr")) < (passive_level+1) else passive_level].find_all("td")] + \
                    [a.get_text().strip() for a in
                     stats_table.find_all("tr")[1].find_all("td")[(-2 if 'Passives' in categories else -1):]]
            stats = [a if a else 'N/A' for a in stats]
            colour = 0xe8e1c9
            if 'Specials' in categories:
                colour = 0xf499fe
            elif 'Assists' in categories:
                colour = 0x1fe2c3

            passive_colours = {1:0xcd914c, 2:0xa8b0b0, 3:0xd8b956}
            skill_name = stats[1 if 'Passives' in categories else 0]

            # use learners table to figure out seal colour
            if 'Seal Exclusive Skills' not in categories:
                learners_table = html.find_all("table", attrs={"class": "sortable"})[-1]
                skill_chain_position, learners = get_learners(learners_table, categories, skill_name)
                if 'Passives' in categories and skill_name[-1] in ['1', '2', '3']:
                    colour = passive_colours[skill_chain_position]
            else:
                if skill_name[-1] in ['1', '2', '3']:
                    colour = passive_colours[int(skill_name[-1])]

            message = discord.Embed(
                title=skill_name,
                url=feh_source % (urllib.parse.quote(arg)),
                color=colour
            )

            if 'Passives' in categories:
                icon = get_icon(stats[1])
                if not icon is None:
                    message.set_thumbnail(url=icon)
                message.add_field(
                name="Slot",
                value=stats_table.th.text.lstrip('Type ')
                )
                message.add_field(
                name="SP Cost",
                value=stats[0]
                )
            else:
                if 'Specials' in categories:
                    message.add_field(
                    name="Cooldown",
                    value=stats[1]
                    )
                elif 'Assists' in categories:
                    message.add_field(
                    name="Range",
                    value=stats[1]
                    )
                message.add_field(
                name="SP Cost",
                value=stats[3]
                )
            message.add_field(
                name="Effect",
                value=stats[2],
                inline=False
            )
            if 'Passives' in categories:
                inherit_r = ', '.join(map(lambda r:r.text, html.ul.find_all('li')))
            else:
                inherit_r = 'Only, '.join(stats[-2].split('Only'))[:(-2 if 'Only' in stats[-2] else None)]
            message.add_field(
                name="Inherit Restrictions",
                value=inherit_r
            )
            if 'Seal Exclusive Skills' not in categories and learners:
                message.add_field(
                    name="Heroes with " + arg,
                    value=learners,
                    inline=False
                )
        else:
            message = discord.Embed(
                title=arg,
                url=feh_source % (urllib.parse.quote(arg)),
                color=0x222222
            )
        await self.bot.say(embed=message)

    flaunt_cache = {}

    @bot.command(pass_context=True, aliases=['flaunt', 'Flaunt', 'Fehflaunt', 'FEHFlaunt'])
    async def fehflaunt(self, ctx):
        """Use this command to show off your prized units.
If you want to add a flaunt please send a screenshot of your unit to monkeybard."""
        user = str(ctx.message.author)
        if user in flaunt:
            if user in self.flaunt_cache:
                f = self.flaunt_cache[user]
            else:
                print("Downloading flaunt for "+user)
                request = urllib.request.Request(flaunt[user] + '?width=384&height=683', headers={'User-Agent': 'Mozilla/5.0'})
                response = urllib.request.urlopen(request)
                f = response.read()
                self.flaunt_cache[user] = f
            f = io.BytesIO(f)
            f.name = os.path.basename(flaunt[user])
            print("Uploading flaunt for "+user)
            await self.bot.upload(f)
        else:
            await self.bot.say("I'm afraid you have nothing to flaunt.")

    @bot.command(pass_context=True, aliases=['stats', 'stat', 'fehstat', 'Stats', 'Stat', 'Fehstat', 'Fehstats', 'FEHstat', 'FEHStat', 'FEHstats', 'FEHStats'])
    async def fehstats(self, ctx, *args):
        """I will calculate the stats of a unit given some parameters.
Possible Parameters (all optional):
                    +[boon], -[bane]: specify a unit's boon and bane where [boon] and [bane] are one of the following: HP, ATK, SPD, DEF, RES. The boon and bane cannot specify the same stat. If a boon or a bane is specified the other must be as well. Default is neutral. Example: +spd -hp
          +[number between 1 and 10]: specify the level of merge a unit is. Default is no merges. Example: +5
                        [c, b, a, s]: specify the level of summoner support the unit has. Default is no support. Example: s
[number/number/number/number/number]: specify any additional modifiers such as modifiers from skills or weapon mt. The order is HP/ATK/SPD/DEF/RES. If you specify less than 5 modifiers, for example 1/1/1, it will add 1 to HP/ATK/SPD only. You can have as many of these as you want. Default is no modifiers. Example: 0/5/-5/0/0
           [number between 1 and 5]*: specify the rarity of the unit. If left unspecified, shows stats for all rarities. Example: 5*
Example usage:
?stats lukas 5* +10 s +def -spd 0/14 0/-3/0/5
will show the stats of a 5* Lukas merged to +10 with +Def -Spd IVs with a Summoner S Support and an additional 14 attack (presumably from a Slaying Lance+) as well as -3 attack and +5 defense (presumably from Fortress Defense)."""
        unit_stats = get_unit_stats(args, sender=str(ctx.message.author))
        if isinstance(unit_stats, tuple):
            unit, base, max = unit_stats
            base = array_to_table(base)
            max = array_to_table(max)
            message = discord.Embed(
                title=unit,
                url=feh_source % (urllib.parse.quote(unit)),
                color=0x222222
            )
            icon = get_icon(unit, "Icon_Portrait_")
            if not icon is None:
                message.set_thumbnail(url=icon)
            message.add_field(
                name="BST",
                value=max[-1]['Total'],
                inline=False
            )
            message.add_field(
                name="Base Stats",
                value=format_stats_table(base),
                inline=True
            )
            message.add_field(
                name="Max Level Stats",
                value=format_stats_table(max),
                inline=True
            )
            await self.bot.say(embed=message)
        else:
            await self.bot.say(unit_stats)

    @bot.command(pass_context=True, aliases=['Fehcompare', 'compare', 'Compare', 'FEHcompare', 'FEHCompare'])
    async def fehcompare(self, ctx, *args):
        """I will compare the max stats of two units with specified parameters.
Please reference ?help fehstats for the kinds of accepted parameters.
Simply type in unit builds as you would with ?fehstats and add a v or vs between the units. Use -q to only show the difference.
Unlike ?fehstats, if a rarity is not specified I will use 5★ as the default."""
        args = list(map(lambda a:a.lower(), args))
        separators = ['v', 'vs', '-v', '&', '|']
        try:
            separator, args = find_arg(args, separators, separators, 'separator', remove=False)
        except ValueError as err:
            # multiple separators
            await self.bot.say("Please use one "+', '.join(list(map(lambda s:'`'+s+'`', separators[:-1]))) +" or `|` to separate the units you wish to compare.")
            return
        # no separators
        if separator is None:
            await self.bot.say("Please use one "+', '.join(list(map(lambda s:'`'+s+'`', separators[:-1]))) +" or `|` to separate the units you wish to compare.")
            return
        quiet_mode = False
        if '-q' in args:
            quiet_mode = True
            args.remove('-q')
        unit1_args = args[:args.index(separator)]
        unit2_args = args[args.index(separator)+1:]
        unit1_stats = get_unit_stats(unit1_args, default_rarity=5, sender=str(ctx.message.author))
        if not isinstance(unit1_stats, tuple):
            await self.bot.say('I had difficulty finding what you wanted for the first unit. ' + unit1_stats)
            return
        unit2_stats = get_unit_stats(unit2_args, default_rarity=5, sender=str(ctx.message.author))
        if not isinstance(unit2_stats, tuple):
            await self.bot.say('I had difficulty finding what you wanted for the second unit. ' + unit2_stats)
            return

        unit1, base1, max1 = unit1_stats
        unit2, base2, max2 = unit2_stats
        if not quiet_mode:
            base1_table = array_to_table(base1)
            max1_table = array_to_table(max1)
            message1 = discord.Embed(
                title=unit1,
                url=feh_source % (urllib.parse.quote(unit1)),
                color=0x222222
            )
            icon = get_icon(unit1, "Icon_Portrait_")
            if not icon is None:
                message1.set_thumbnail(url=icon)
            message1.add_field(
                name="BST",
                value=max1_table[-1]['Total'],
                inline=False
            )
            message1.add_field(
                name="Base Stats",
                value=format_stats_table(base1_table),
                inline=True
            )
            message1.add_field(
                name="Max Level Stats",
                value=format_stats_table(max1_table),
                inline=True
            )
            base2_table = array_to_table(base2)
            max2_table = array_to_table(max2)
            message2 = discord.Embed(
                title=unit2,
                url=feh_source % (urllib.parse.quote(unit2)),
                color=0x222222
            )
            icon = get_icon(unit2, "Icon_Portrait_")
            if not icon is None:
                message2.set_thumbnail(url=icon)
            message2.add_field(
                name="BST",
                value=max2_table[-1]['Total'],
                inline=False
            )
            message2.add_field(
                name="Base Stats",
                value=format_stats_table(base2_table),
                inline=True
            )
            message2.add_field(
                name="Max Level Stats",
                value=format_stats_table(max2_table),
                inline=True
            )
            await self.bot.say(embed=message1)
            await self.bot.say(embed=message2)
        max1 = np.array(list(filter(lambda r:any(r), max1))[0])
        max2 = np.array(list(filter(lambda r:any(r), max2))[0])
        difference = max1 - max2
        bst_diff = difference.sum()
        if any(difference):
            await self.bot.say("%s compared to %s: %s%s" %\
             (unit1, unit2, ', '.join(['%s: **%s%d**' % (stats[i], '+' if difference[i]>0 else '', difference[i]) for i in range(5) if difference[i]]), (', BST: **%s%d**' % ('+' if bst_diff>0 else '', bst_diff)) if bst_diff else ''))
        else:
            await self.bot.say("There appears to be no difference between these units!")

    @bot.command(aliases=['list', 'List', 'Fehlist', 'FEHlist', 'FEHList'])
    async def fehlist(self, *args):
        """I will create a list of heroes to serve your needs.
Usage: fehlist|list [-f filters] [-s fields_to_sort_by] [-r (reverse the results)]
Filters reduce the list down to the heroes you want. You can filter by Colour (Red, Blue, Green, Colourless), Weapon (Sword, Lance, Axe, Bow, Dagger, Staff, Tome, Breath) or Movement Type (Infantry, Cavalry, Flying, Armored). You can also filter by a stat threshold such as (HP>30) or (DEF+RES>50).
Sorting fields let you choose how to sort the heroes. You can sort highest first in any stat (HP, ATK, SPD, DEF, RES, BST (Total)) or alphabetically by Name, Colour, Weapon or Movement Type. You can also sort by added stat totals such as (DEF+RES) or (ATK+SPD). The order you declare these will be the order of priority.
There are shorthands to make it easier:
Red, Blue, Green, Colourless = r, b, g, c
Sword, Lance, Axe, Bow, Dagger, Staff, Tome, Breath = sw, la, ax, bo, da, st, to, br
Infantry, Cavalry, Flying, Armored = in, ca, fl, ar
Name, Colour, Weapon, Movement Type = na, co, we, mov
Or you can just type out the full name.
Sorting by an added stat total is as simple as typing in all the stats you want to add with a + between them without spaces. Examples: atk+def+spd def+res
You can filter by a stat or an added stat total by typing the stat(s) as you would for sort and adding a comparison and number. Examples: hp>30 spd<20 def>=30 atk==35 atk=35 hp+spd>60
Example: !list -f red sword infantry -s attack hp
         is the same as
         !list -f r sw in -s atk hp
         and will produce a list of units that are Red, wield Swords and are Infantry sorted by Attack and then by HP."""
        if args:
            if (len(args) > 1 and '-r' in args and '-f' not in args and '-s' not in args) or ('-r' not in args and '-f' not in args and '-s' not in args) or (args[0] not in ['-r', '-f', '-s']):
                await self.bot.say('Unfortunately I had trouble figuring out what you wanted. Are you sure you typed the command correctly?\n```Usage: fehlist|list [-f filters] [-s fields_to_sort_by] [-r]```')
                return

        # set up argument parser
        parser = argparse.ArgumentParser(description='Process arguments for heroes list.')
        parser.add_argument('-f', nargs='*')
        parser.add_argument('-s', nargs='*')
        parser.add_argument('-r', action='store_const', const=False, default=True)
        args = vars(parser.parse_args(args=args))
        filters = {}
        if args['f']:
            filters = standardize(args, 'f')
            if filters is None:
                await self.bot.say('Invalid filters or multiple filters for the same field were selected.')
                return
        sort_keys = []
        if args['s']:
            sort_keys = standardize(args, 's')
            if sort_keys is None:
                await self.bot.say('Invalid fields to sort by were selected.')
                return
        try:
            heroes = get_heroes_list()
        except urllib.error.HTTPError as err:
            if err.code == 500:
                await self.bot.say("Unfortunately, it seems like I cannot access my sources at the moment. Please try again later.")
                return

        for f in filters:
            if f != 'Threshold':
                heroes = list(filter(lambda h:h[f] in filters[f], heroes))
            else:
                for t in filters[f]:
                    heroes = list(filter(lambda h:t[0](list(itertools.accumulate([h[field] for field in t[1]]))[-1], t[2]), heroes))
        if not heroes:
            await self.bot.say('No results found for selected filters.')
            return
        await self.bot.say('Results found: %d' % len(heroes))
        for key in reversed(sort_keys):
            heroes = sorted(heroes,
                            key=lambda h:
                                list(
                                    itertools.accumulate([h[field] for field in key] if isinstance(key, tuple) else [h[key]]))[-1],
                                    reverse=not args['r'] if key in ['Name', 'Movement', 'Colour', 'Weapon'] else args['r']
                                    )
        list_string = ', '.join([
            h['Name'] + (
                (' ('+','.join([
                    str(
                        list(itertools.accumulate([h[field] for field in k] if isinstance(k, tuple) else [h[k]]))[-1]
                        ) for k in sort_keys if k != 'Name'
                    ])+')' if sort_keys else '')
                if len(sort_keys) != 1 or sort_keys[0] != 'Name' else ''
                ) for h in heroes
            ])
        while len(list_string) > 2000:
            list_string = ', '.join([
                h['Name'] + (
                    (' ('+','.join([
                        str(
                            list(itertools.accumulate([h[field] for field in k] if isinstance(k, tuple) else [h[k]]))[-1]
                            ) for k in sort_keys if k != 'Name'
                        ])+')' if sort_keys else '')
                    if len(sort_keys) != 1 or sort_keys[0] != 'Name' else ''
                    ) for h in heroes
                ])
            heroes = heroes[:-1]
        message = list_string
        await self.bot.say(message)


def setup(bot):
    bot.add_cog(MagikarpJump(bot))
    bot.add_cog(FireEmblemHeroes(bot))
