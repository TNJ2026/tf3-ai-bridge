import copy
import pytest
from no_gui_soak import compare_map_identity


def sample():
    return {'width': 1000, 'height': 1000,
            'towns': [{'id': 1, 'name': 'Town', 'position': {'x': 1, 'y': 2}}],
            'industries': [{'id': 2, 'fileName': 'farm.con', 'position': {'x': 3, 'y': 4}}]}


def test_strictly_additive_industry_is_explicitly_reconciled():
    before = sample(); after = copy.deepcopy(before)
    after['industries'].append({'id': 3, 'fileName': 'forest.con', 'position': {'x': 5, 'y': 6}})
    result = compare_map_identity(before, after)
    assert result['allOriginalObjectsPreserved']
    assert result['industryAdditions'][0]['id'] == 3


@pytest.mark.parametrize('change', ['removed', 'moved', 'resource', 'id', 'duplicate', 'town', 'size'])
def test_identity_changes_are_not_hidden(change):
    before = sample(); after = copy.deepcopy(before)
    if change == 'removed': after['industries'] = []
    if change == 'moved': after['industries'][0]['position']['x'] += 1
    if change == 'resource': after['industries'][0]['fileName'] = 'other.con'
    if change == 'id': after['industries'][0]['id'] = 3
    if change == 'duplicate': after['industries'].append(copy.deepcopy(after['industries'][0]))
    if change == 'town': after['towns'].append({'id': 3, 'name': 'Other', 'position': {'x': 5, 'y': 6}})
    if change == 'size': after['width'] = 2000
    with pytest.raises(ValueError): compare_map_identity(before, after)


def test_nested_runner_failure_keeps_actual_cause():
    from no_gui_soak import describe_failure
    exc=ExceptionGroup('task group', [ExceptionGroup('nested', [ValueError('Map entity removed: 42')])])
    assert describe_failure(exc)=='ValueError: Map entity removed: 42'
