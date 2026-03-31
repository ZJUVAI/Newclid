#!/usr/bin/env python3
"""Helper to parse llm_input_renamed format."""

import re
from typing import List, Tuple

def parse_llm_input(llm_input: str) -> Tuple[List[str], str]:
    """Parse llm_input_renamed to extract premises and goal.
    
    Format: <problem> a : ; b : ; ... h : premise1 premise2 ; ... ? goal </problem>
    
    Returns:
        (premises, goal) where premises is a list of predicate strings
    """
    # Remove tags
    text = llm_input.replace("<problem>", "").replace("</problem>", "").strip()
    
    # Split by "?"
    if "?" not in text:
        raise ValueError("No goal separator '?' found")
    
    premise_part, goal_part = text.split("?", 1)
    goal = goal_part.strip()
    
    # Parse premises
    # Format: "a : ; b : ; ... h : premise1 [tag1] premise2 [tag2] ; ..."
    premises = []
    
    # Remove all [xxx] tags
    premise_part = re.sub(r'\[\d+\]', '', premise_part)
    
    # Split by ";" to get clauses
    clauses = premise_part.split(";")
    
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        
        # Check if it's a point declaration or premise clause
        if ":" in clause:
            # Format: "point_name : premise1 premise2 ..."
            parts = clause.split(":", 1)
            if len(parts) == 2:
                point_name = parts[0].strip()
                premise_text = parts[1].strip()
                
                if premise_text:  # Has premises
                    # Known predicate names
                    pred_names = ['eqangle', 'cong', 'perp', 'para', 'coll', 'cyclic', 
                                  'midp', 'eqratio', 'simtri', 'contri', 'rconst', 'aconst']
                    
                    # Find all predicates using regex
                    for pred_name in pred_names:
                        # Match: pred_name followed by space-separated single letters
                        pattern = rf'{pred_name}\s+([a-z\s]+?)(?=\s+(?:{"|".join(pred_names)})|$)'
                        matches = re.finditer(pattern, premise_text)
                        
                        for match in matches:
                            pred_str = match.group(0).strip()
                            # Clean up extra spaces
                            pred_str = " ".join(pred_str.split())
                            if pred_str:
                                premises.append(pred_str)
    
    return premises, goal


# Test
if __name__ == "__main__":
    test_input = "<problem> a : ; b : ; c : ; d : ; e : ; f : ; g : ; h : eqangle a h b h d g d f [000] cong c f e h [001] ; i : eqangle a i b i d g d f [002] cong c f e i [003] ? eqangle a h a i b h b i </problem>"
    
    premises, goal = parse_llm_input(test_input)
    print("Premises:")
    for p in premises:
        print(f"  {p}")
    print(f"\nGoal: {goal}")
