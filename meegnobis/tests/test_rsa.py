"""Module containing test for rsa"""

import pytest
import numpy as np
from numpy.testing import assert_array_equal, assert_equal, \
    assert_array_almost_equal
from sklearn.model_selection import StratifiedShuffleSplit
from scipy.spatial.distance import cdist

from ..rsa import mean_group, _compute_fold, compute_temporal_rdm,\
    make_pseudotrials, fisher_correlation
from ..testing import generate_epoch

rng = np.random.RandomState(42)


def test_mean_group():
    n_epochs_cond = 5
    n_conditions = 2
    epoch = generate_epoch(n_epochs_cond=n_epochs_cond,
                           n_conditions=n_conditions)
    array = epoch.get_data()
    targets = epoch.events[:, 2]

    avg_array, unique_targets = mean_group(array, targets)
    assert_array_equal(unique_targets, [0, 1])
    assert_array_equal(avg_array, np.asanyarray([array[:5].mean(axis=0),
                                                 array[5:].mean(axis=0)]))


@pytest.mark.parametrize("cv_normalize_noise", [None, 'epoch', 'baseline'])
def test_compute_fold(cv_normalize_noise):
    n_epochs_cond = 10
    n_conditions = 4
    epoch = generate_epoch(n_epochs_cond=n_epochs_cond,
                           n_conditions=n_conditions)
    targets = epoch.events[:, 2]
    train = [np.arange(n_epochs_cond / 2) + i*n_epochs_cond
             for i in range(n_conditions)]
    test = [np.arange(n_epochs_cond / 2, n_epochs_cond) + i*n_epochs_cond
            for i in range(n_conditions)]
    train = np.array(train).flatten().astype(int)
    test = np.array(test).flatten().astype(int)

    rdms, target_pairs = _compute_fold(
        epoch, targets, train, test, cv_normalize_noise=cv_normalize_noise)
    n_times = len(epoch.times)
    n_pairwise_conditions = n_conditions * (n_conditions - 1)/2 + n_conditions
    assert(rdms.shape == (n_pairwise_conditions, n_times, n_times))
    assert(rdms.shape[0] == len(target_pairs))
    # target_pairs should be already sorted
    target_pairs_sorted = sorted(target_pairs)
    assert_array_equal(target_pairs, target_pairs_sorted)
    # we should only get the upper triangular with the diagonal
    unique_targets = np.unique(targets)
    target_pairs_ = []
    for i_tr, tr_lbl in enumerate(unique_targets):
        for i_te, te_lbl in enumerate(unique_targets[i_tr:]):
            target_pairs_.append('+'.join(map(str, [tr_lbl, te_lbl])))
    assert_array_equal(target_pairs_, target_pairs)

    # check that it fails if the targets are strings
    targets = map(str, targets)
    with pytest.raises(ValueError):
        rdms = _compute_fold(epoch, targets, train, test,
                             cv_normalize_noise=cv_normalize_noise)


def test_compute_fold_valuerrorcov():
    with pytest.raises(ValueError):
        n_epochs_cond = 10
        n_conditions = 4
        epoch = generate_epoch(n_epochs_cond=n_epochs_cond,
                               n_conditions=n_conditions)
        targets = epoch.events[:, 2]
        train = [np.arange(n_epochs_cond / 2) + i*n_epochs_cond
                 for i in range(n_conditions)]
        test = [np.arange(n_epochs_cond / 2, n_epochs_cond) + i*n_epochs_cond
                for i in range(n_conditions)]
        train = np.array(train).flatten().astype(int)
        test = np.array(test).flatten().astype(int)

        _ = _compute_fold(epoch, targets, train, test,
                          cv_normalize_noise='thisshouldfail')


def test_compute_fold_values():
    n_epochs_cond = 1
    n_conditions = 4
    n_times = 10
    epoch = generate_epoch(n_epochs_cond=n_epochs_cond,
                           n_conditions=n_conditions,
                           n_times=n_times)
    targets = epoch.events[:, 2]
    # let's use the same train and test
    train = test = np.arange(len(targets))

    rdms, target_pairs = _compute_fold(epoch, targets,
                                       train, test, metric_fx=cdist)

    epo_data = epoch.get_data()
    for i_tr in range(n_times):
        for i_te in range(n_times):
            rdms_ = cdist(epo_data[..., i_tr], epo_data[..., i_te])
            # impose symmetry
            rdms_ += rdms_.T
            rdms_ /= 2.
            assert_array_equal(rdms[:, i_tr, i_te],
                               rdms_[np.triu_indices_from(rdms_)])


@pytest.mark.parametrize("cv_normalize_noise", [None, 'epoch', 'baseline'])
def test_compute_temporal_rdm(cv_normalize_noise):
    n_epochs_cond = 20
    n_conditions = 4
    epoch = generate_epoch(n_epochs_cond=n_epochs_cond,
                           n_conditions=n_conditions)
    cv = StratifiedShuffleSplit(n_splits=4, test_size=0.5)

    rdm, target_pairs = compute_temporal_rdm(
        epoch, cv=cv, targets=epoch.events[:, 2],
        cv_normalize_noise=cv_normalize_noise)
    n_times = len(epoch.times)
    n_pairwise_conditions = n_conditions * (n_conditions - 1)/2 + n_conditions
    assert(rdm.shape == (n_pairwise_conditions, n_times, n_times))
    assert(rdm.shape[0] == len(target_pairs))


def test_make_pseudotrials():
    n_epochs_cond = 20
    n_conditions = 4
    epoch = generate_epoch(n_epochs_cond=n_epochs_cond,
                           n_conditions=n_conditions)

    targets = epoch.events[:, 2]
    epoch_data = epoch.get_data()
    navg = 4
    avg_trials, avg_targets = make_pseudotrials(epoch_data, targets, navg=navg)
    # check we get the right shape of the data
    assert_equal(avg_trials.shape[0], -(-epoch_data.shape[0]//navg))
    assert_array_equal(avg_trials.shape[1:], epoch_data.shape[1:])
    assert_equal(len(avg_targets), len(avg_trials))
    assert_equal(len(np.unique(avg_targets)), n_conditions)

    # check we have randomization going on
    avg_trials2, avg_targets2 = make_pseudotrials(epoch_data, targets,
                                                  navg=navg)
    assert_array_equal(avg_targets, avg_targets2)
    assert(not np.allclose(avg_trials, avg_trials2))

    # check it works even with an odd number of trials
    epoch_data = epoch_data[1:]
    targets = targets[1:]
    # just to be sure it's odd
    assert(len(targets) % 2 == 1)
    assert(len(epoch_data) % 2 == 1)
    avg_trials, avg_targets = make_pseudotrials(epoch_data, targets, navg=navg)
    assert_equal(avg_trials.shape[0], -(-epoch_data.shape[0]//navg))
    assert_equal(len(np.unique(avg_targets)), n_conditions)
    assert_equal(len(avg_targets), len(avg_trials))


def test_fisher_correlation():
    for _ in range(10):
        x = np.random.randn(1, 20)
        y = x + np.random.randn(*x.shape)/10000
        out = np.tanh(fisher_correlation(x, y))[0]
        assert_array_almost_equal([1], out)
        assert_array_almost_equal(np.corrcoef(x, y)[0, 1], out[0])





