
import numpy as np

from dialent.common.metrics import Metrics

#########################################################################################

class TagData:
    """Utility object that contains data regarding a set of objects currently processed
    by EvaluationMatrix"""

    def __init__(self, tag, object_list):
        """Loads an object list with the given tag from the larger object_list"""
        self.tag = tag
        self.objects = sorted([x for x in object_list if x.tag == tag],
                              key=lambda x: x.id)
        self.size = len(self.objects)
        self._start = 0

    def start(self):
        return self._start

    def end(self):
        return self._start + self.size


class EvaluationMatrix:
    """Matrix built out of object pair quality that finds an optimal matching"""

    allowed_tags = ['per', 'loc', 'org', 'locorg']

    def __init__(self, std, test, calc, mode='regular',):
        """Initialize the matrix.
        
        std and test must be lists of objects from standard and test respectively
        mode must be either 'regular' or 'simple' and it determines whether locorgs are
        matched with orgs and locs or not
        calc must be a priority/quality calculator object that supports values of """

        assert(mode == 'regular' or mode == 'simple')
        self.mode = mode
        self.metrics = {}

        self.s = {}
        self.t = {}
        for tag in EvaluationMatrix.allowed_tags:
            self.s[tag] = TagData(tag, std)
            self.t[tag] = TagData(tag, test)

        # finalize the offsets
        for i in range(1, len(EvaluationMatrix.allowed_tags)):
            prev_tag = EvaluationMatrix.allowed_tags[i-1]
            tag = EvaluationMatrix.allowed_tags[i]
            self.s[tag]._start = self.s[prev_tag].end()
            self.t[tag]._start = self.t[prev_tag].end()

        self.std = []
        self.test = []
        for tag in EvaluationMatrix.allowed_tags:
            self.std.extend(self.s[tag].objects)
            self.test.extend(self.t[tag].objects)

        self.n_std = len(self.std)
        self.n_test = len(self.test)

        self.m = np.zeros((self.n_std, self.n_test))
        self.calc = calc

        for i, x in enumerate(self.std):
            for j, y in enumerate(self.test):
                self.m[i][j] = self.calc.priority(x, y)

    def findSolution(self):
        """Runs the recursive search to find an optimal matching"""
        
        q, matching = self._recursiveSearch(
            [i for i in range(self.n_std)],
            [j for j in range(self.n_test)],
            []
            )

        self.metrics['overall'] = self._evaluate(matching)
        for tag in EvaluationMatrix.allowed_tags:
            self.metrics[tag] = self._evaluate(matching, tag)

        return matching

    def _recursiveSearch(self, std, test, pairs):
        """
            Run a recursive search of the optimal matching.

            Returns the following tuple: (overall quality, matching)

            std - remaining standard indices list
            test - remaining test indices list
            pairs - current list of built pairs
        """
        if len(std) == 0 or len(test) == 0:
            # final step, evaluate the matching
            metrics = self._evaluate(pairs)
            return metrics.f1, pairs

        curr = std[0]
        max_res = None

        possible_pairs_count = 0
        pair_max_alternatives = 0

        for t in self._findMatches(curr, test):
            i = test.index(t)

            # let's see what other matching options does this test object have
            # this is necessary to check conditions for the logic below
            possible_pairs_count += 1
            alt_count = 0
            skip_test_object = False
            for k in std:
                if self.m[k, t] == 1 and self.m[curr, t] < 1:
                    # test objects that have some other perfect matching must be skipped
                    skip_test_object = True
                if self.m[k, t] != 0:
                    alt_count += 1
                if alt_count > pair_max_alternatives:
                    pair_max_alternatives = alt_count
                
            if skip_test_object:
                continue

            # try to confirm the pair
            res = self._recursiveSearch(
                std[1:], test[:i] + test[i+1:],
                pairs + [(curr, t)])
            if max_res is None or res[0] > max_res[0]:
                max_res = res

        # check what would happen if this standard object were ignored
        # this check is obviously performance-heavy and only necessary under
        # these conditions
        if (possible_pairs_count == 0 or
                possible_pairs_count == 1 and pair_max_alternatives > 1):
            res = self._recursiveSearch(
                std[1:], test,
                pairs)
            if max_res is None or res[0] > max_res[0]:
                max_res = res

        return max_res

    def _findMatches(self, s_index, test):
        """Finds a list of possible matches for the standard object with the given index
        within the list of available test objects.
        
        Returns a list of test object indices
        
        According to the documentation, any perfectly fitting objects MUST be matched"""
        perfect_matches = [t for t in test if self.m[s_index, t] == 1]
        matches = [t for t in test if self.m[s_index, t] != 0] 
        return perfect_matches if len(perfect_matches) > 0 else matches

    def _evaluate(self, pairs, tag_filter = ''):
        tp = 0

        if tag_filter in EvaluationMatrix.allowed_tags:
            subset = self._reduce(pairs, tag_filter)
            n_std = self.s[tag_filter].size
            n_test = self.t[tag_filter].size
        else:
            subset = pairs
            n_std = self.n_std
            n_test = self.n_test

        for pair in subset:
            tp += self.calc.quality(self.std[pair[0]], self.test[pair[1]])

        return Metrics.createSimple(tp, n_std, n_test)

    def _reduce(self, matching, tag):
        """Returns a sub-matching corresponding to the given tag"""
        res = []
        for _s, _t in matching:
            if _s >= self.s[tag].start() and _s < self.s[tag].end():
                res.append((_s, _t))
        return res