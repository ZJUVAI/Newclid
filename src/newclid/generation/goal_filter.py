import logging
import random
import re
import time

from newclid.statement import Statement

class GeometryGoalFilter:
    def naive_goal_filter(self, goal_name, goal_args, dep_graph):
        if goal_name == 'cong':
            return self._naive_cong_filter(goal_args, dep_graph)
        elif goal_name == 'para':
            return self._naive_para_filter(goal_args, dep_graph)
        elif goal_name == 'coll':
            return True
        elif goal_name == 'perp':
            return True
        elif goal_name == 'cyclic':
            return True
        elif goal_name == 'eqratio':
            return self._naive_eqratio_filter(goal_args, dep_graph)
        elif goal_name == 'eqangle':
            return self._naive_eqangle_filter(goal_args, dep_graph)
        elif goal_name == 'acompute':
            return True
        elif goal_name == 'aconst':
            return self._naive_aconst_filter(goal_args, dep_graph)
        elif goal_name == 'rcompute':
            return True
        elif goal_name == 'rconst':
            return self._naive_rconst_filter(goal_args, dep_graph)
        elif goal_name == 'simtri' or goal_name == 'simtrir':
            return self._naive_simtri_filter(goal_args, dep_graph)
        elif goal_name == 'contri' or goal_name == 'contrir':
            return self._naive_contri_filter(goal_args, dep_graph)
        return False
    def _naive_cong_filter(self, args, dep_graph):
        # case: cong AB = AB,
        seg1 = {args[0], args[1]}
        seg2 = {args[2], args[3]}
        if seg1 == seg2:
            return False
        return True
    
    def _naive_para_filter(self, args, dep_graph):
        # case: para AB ∥ AC => coll
        if len(set(args)) < 4:
            return False
        return True
    
    def _naive_simtri_filter(self, args, dep_graph):
        # case: simtri △ABC ≅ △ABC
        tri_1 = {args[0], args[1], args[2]}
        tri_2 = {args[3], args[4], args[5]}
        if tri_1 == tri_2:
            return False
        sm = Statement.from_tokens(['contri']+args, dep_graph)
        if sm.check():
            return False
        sm = Statement.from_tokens(['contrir']+args, dep_graph)
        if sm.check():
            return False
        return True
    
    def _naive_contri_filter(self, args, dep_graph):
        # case: contri △ABC ≅ △ABC
        tri_1 = {args[0], args[1], args[2]}
        tri_2 = {args[3], args[4], args[5]}
        if tri_1 == tri_2:
            return False
        return True
    
    def _naive_eqangle_filter(self, args, dep_graph):
        seg_1 = {args[0], args[1]}
        seg_2 = {args[2], args[3]}
        seg_3 = {args[4], args[5]}
        seg_4 = {args[6], args[7]}

        a1_args = list(set(args[:4]))
        a2_args = list(set(args[4:]))
        if not (len(a1_args) == 3 and len(a2_args)) == 3:
            return False

        # case: eqangle ∠(AB,AB) = ∠(CD,EF) => para CD∥EF
        if seg_1 == seg_2 or seg_3 == seg_4:
            return False
        
        # case: eqangle ∠(AB,CD) = ∠(AB,CD)
        if seg_1 == seg_3 and seg_2 == seg_4:
            return False
        
        # case: eqangle ∠(AB,CD) = ∠(CD,AB) => perp AB⊥CD
        if seg_1 == seg_4 and seg_2 == seg_3:
            return False
        
        # case: angles with accurate degree
        parallel_sets = [
            [args[0], args[1], args[2], args[3]],
            [args[0], args[1], args[4], args[5]],
            [args[0], args[1], args[6], args[7]],
            [args[2], args[3], args[4], args[5]],
            [args[2], args[3], args[6], args[7]],
            [args[4], args[5], args[6], args[7]],
        ]
        for arg_set in parallel_sets:
            sm = Statement.from_tokens(['acompute'] + arg_set, dep_graph)
            if sm and sm.check():
                return False
        for arg_set in parallel_sets:
            sm = Statement.from_tokens(['para'] + arg_set, dep_graph)
            if sm.check():
                return False
        for arg_set in parallel_sets:    
            sm = Statement.from_tokens(['perp'] + arg_set, dep_graph)
            if sm.check():
                return False       
        
        # case: simtri
        # a1_args = list(set(args[:4]))
        # a2_args = list(set(args[4:]))
        # if len(a1_args) == 3 and len(a2_args) == 3:
        #     simtri_sets = [
        #         [*a1_args, *a2_args],
        #         [*a1_args, a2_args[0], a2_args[2], a2_args[1]],
        #         [*a1_args, a2_args[1], a2_args[0], a2_args[2]],
        #         [*a1_args, a2_args[1], a2_args[2], a2_args[0]],
        #         [*a1_args, a2_args[2], a2_args[0], a2_args[1]],
        #         [*a1_args, a2_args[2], a2_args[1], a2_args[0]]
        #     ]
        #     for simtri_set in simtri_sets:
        #         sm = Statement.from_tokens(['simtri']+simtri_set, dep_graph)
        #         if sm.check():
        #             return False
        #     for simtri_set in simtri_sets:
        #         sm = Statement.from_tokens(['simtrir']+simtri_set, dep_graph)
        #         if sm.check():
        #             return False
        return True

    def _naive_eqratio_filter(self, args, dep_graph):
        seg_1 = {args[0], args[1]}
        seg_2 = {args[2], args[3]}
        seg_3 = {args[4], args[5]}
        seg_4 = {args[6], args[7]}

        # two segments are the same
        # case: eqratio AB/AB = CD/EF => cong CD = EF
        if seg_1 == seg_2 or seg_3 == seg_4:
            return False
        
        # case: eqratio AB/CD = AB/CD
        # case: eqratio AB/CD = AB/EF => cong CD = EF
        if seg_1 == seg_3 or seg_2 == seg_4:
            return False
        
        # case: eqratio AB/CD = CD/AB => cong AB = CD        
        if seg_1 == seg_4 and seg_3 == seg_4:
            return False
        
        # two segments with the same length
        sets = [
            [args[0], args[1], args[2], args[3]],
            [args[0], args[1], args[4], args[5]],
            [args[2], args[3], args[6], args[7]],
            [args[4], args[5], args[6], args[7]],
        ]
        for arg_set in sets:
            sm = Statement.from_tokens(['cong'] + arg_set, dep_graph)
            if sm.check():
                return False
            for ratio in ('1/1',):
                sm = Statement.from_tokens(['rconst'] + arg_set + [ratio], dep_graph)
                if sm.check():
                    return False
            sm = Statement.from_tokens(['rcompute'] + arg_set, dep_graph)
            if sm.check():
                return False
            
        return True

    def _naive_rconst_filter(self, args, dep_graph):
        if args[-1] == '1/1':
            return False
        return True

    def _naive_aconst_filter(self, args, dep_graph):
        if args[-1] in ('0pi/1', '1pi/2', '1pi/1', '1pi/3', '2pi/3', '1pi/4', '3pi/4'):
            return False
        return True

    def goal_filter(self, possible_goals, dep_graph):
        def group_equivalent_predicates(goals, predicate_type):
            """
            Group equivalent predicate goals together.
            
            Two predicate statements are considered equivalent if they represent
            the same relationship, even with different point orderings.
            """
            # Groups of equivalent pairs
            predicate_groups = []  
            # Corresponding goal objects for each group
            goal_groups = []   
            
            for goal in goals:
                # Extract point names from the goal arguments
                args = [arg.name for arg in goal.args]
                # Each predicate has 8 args representing two relationships
                # First relationship: args[0:4], Second relationship: args[4:8]
                
                found_group = False
                # Check if this goal belongs to an existing group
                for i, (group, goal_group) in enumerate(zip(predicate_groups, goal_groups)):
                    for existing_pair in group:
                        # Check if the relationships in this goal are equivalent to 
                        # relationships in the existing group
                        sm1 = Statement.from_tokens([predicate_type] + args[:4] + existing_pair, dep_graph)
                        sm2 = Statement.from_tokens([predicate_type] + args[4:] + existing_pair, dep_graph)
                        if sm1.check() or sm2.check():
                            found_group = True
                            # Add first relationship to group if not already present
                            if args[:4] not in group:
                                group.append(args[:4])
                            # Add second relationship to group if not already present
                            if args[4:] not in group:
                                group.append(args[4:])
                            # Add goal to corresponding goal group
                            goal_group.append(goal)
                            break
                    if found_group:
                        break
                
                # If no existing group was found, create a new one
                if not found_group:
                    predicate_groups.append([args[:4], args[4:]])
                    goal_groups.append([goal])
            
            return goal_groups
        
        def check_equivalence(p1, p2, token_type):
            args1 = [arg.name for arg in p1.args]
            args2 = [arg.name for arg in p2.args]
            statements = [
                Statement.from_tokens(
                    [token_type, args1[i], args1[i + 1], args2[i], args2[i + 1]], dep_graph)
                for i in range(0, len(args1), 2)
            ]
            return all(sm.check() for sm in statements)

        def remove_duplicates(goals, equivalence_fn, token_type):
            unique_goals = []
            for goal in goals:
                if not any(equivalence_fn(existing_goal, goal, token_type) for existing_goal in unique_goals):
                    unique_goals.append(goal)
            return unique_goals
        
        filtered_goals = []
        for goal in possible_goals:
            parts = goal.to_str().split(" ")
            if self.naive_goal_filter(parts[0], parts[1:], dep_graph):
                filtered_goals.append(goal)
        possible_goals = filtered_goals

        eqangle_goals = [
            goal for goal in possible_goals 
            if goal.predicate.NAME == 'eqangle'
        ]

        eqratio_goals = [
            goal for goal in possible_goals 
            if goal.predicate.NAME == 'eqratio'
        ]

        other_goals = [
            goal for goal in possible_goals 
            if goal.predicate.NAME not in (
                'eqangle', 'eqratio', 'eqratio3',
                # 'simtri', 'contri', 'simtrir', 'contrir',
                'ncoll', 'midp',
                'acompute', 'rcompute',
                'sameside', 'sameclock',
            )
        ]

        # eqangle_goals_groups = group_equivalent_predicates(eqangle_goals, 'eqangle')
        # eqangle_goals = [random.choice(group) for group in eqangle_goals_groups]

        # eqratio_goals_groups = group_equivalent_predicates(eqratio_goals, 'eqratio')
        # eqratio_goals = [random.choice(group) for group in eqratio_goals_groups]

        # eqangle_goals = remove_duplicates(eqangle_goals, check_equivalence, 'para')
        # eqratio_goals = remove_duplicates(eqratio_goals, check_equivalence, 'cong')
        
        return eqangle_goals + eqratio_goals + other_goals

    def aux_predicates_valid_check(self, llm_output: str) -> bool:

        def is_valid(statement: str, valid_predicates: set) -> bool:
            prefix_match = re.match(r"(x00 \w+)\s*:\s*(.*)", statement)
            if prefix_match:
                # coll a c e [002] coll b d e [003]
                rest = prefix_match.group(2)
                segments = re.split(r"\s*\[\d+\]", rest)
                # 'coll a c e' , 'coll b d e'
                segments = [seg.strip() for seg in segments if seg.strip()]
                for segment in segments:
                    parts = segment.split()
                    if parts and parts[0] not in valid_predicates:
                        logging.debug(
                            f"Invalid auxiliary predicate: {parts[0]}")
                        return False
            return True

        # <aux> x00 c : perp k n n s [024] cong k n n s [025]; x00 h : ; x00 i : ; x00 j : perp h i h j [009] cong h i h j [010] ; </aux> <proof> cong a k c k [002] r19 [000] [001] ; cong b k c k [003] r19 [000] [001] ; cong a k b k [004] a00 [002] [003] ; </proof>
        valid_aux_predicates = {'perp', 'para', 'cong', 'coll', 'eqangle', 'cyclic', 'midp'}
        aux_match = re.match(r"<aux>\s*(.*)\s*</aux>", llm_output)
        # c : perp a c b c [001] ; c : perp a c b c [001] ;
        if aux_match:
            aux_content = aux_match.group(1)
            for content_item in aux_content.split(';'):
                content_item = content_item.strip()
                if content_item:
                    if not is_valid(content_item, valid_aux_predicates):
                        return False
        return True