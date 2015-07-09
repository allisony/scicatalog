import pandas as pd
import os
import numpy as np
from warnings import warn
import time

class SciCatalog:
    """
    A class of objects intended to store, modify, and display tabular scientific data with positive and negative errors
    and references.

    Catalogs are stored as a directory containing four (at present) csv files: one each for the values,
    positive errors, negative errors, and references.

    Written by Parke Loyd, 2015/07/08

    I'm hoping to eventually expand this with methods to quickly make pretty LaTeX tables and such and maybe
    accomodate multiple values or references for a single entry (though that would be difficult).
    """

    keys = ['value', 'errpos', 'errneg', 'ref']
    tableFiles = ['values', 'errors_positive', 'errors_negative', 'references']
    fileSuffix = 'csv'
    nullValues = [np.nan, np.nan, np.nan, 'none']
    refDictFile = 'reference_dictionary'
    refFileSuffix = 'txt'

    def __init__(self, path, values=None, errpos=None, errneg=None, refs=None, refDict={}, index=None, columns=None):
        """
        Creates an empty SciCatalog object by intializing the four pandas DataFrame tables and a reference dictionary
        that are kept synced to the disk as changes are made.

        Parameters
        ----------
        path : string
            Path of the directory in which the table files exist or are to be created.
        values, errpos, errneg, refs :
            Data to be put into DataFrames. Each will be used as the `data` keyword argument to instantiate a
            pandas DataFrame. Can be lots of different data types (array, dictionary, DataFrame,
            ... see pandas.DataFrame docs)
        refDict : dict
            A dictionary defining the various reference keys used. This is intended both for brevity in the reference
            table and possibly later use with BibTex... not sure if that will ever come to fruition in a useful way.

        Other **kwargs will be passed along to DataFrame call. See DataFrame documentation for info, but important
        ones include index and columns for providing lists of indices and column names.

        Returns
        -------
        SciCatalog object.

        """

        if os.path.exists(path) and values is not None:
            raise Exception('A directory named {} already exists at {}. You must use a different name or manually '
                            'delete that directory before you an create the catalog you want at that disk location. '
                            ''.format(*os.path.split(path)))

        # store auxilliary data
        self.path = path
        self.paths  = self._tablepaths(path)
        self.archive = os.path.join(path, 'archive')
        self.refDict = refDict
        self.refDictPath = os.path.join(path, self.refDictFile) + '.' + self.refFileSuffix

        # either load or create the SciCat table as appropriate
        if os.path.exists(path):
            self.tables = [pd.DataFrame.from_csv(p) for p in self.paths]
            self.values, self.errpos, self.errneg, self.refs = self.tables

            refs, defs = [], []
            with open(self.refDictPath) as f:
                lines = f.read().splitlines()
                pairs = [line.split(' : ') for line in lines]
            self.refDict = dict(pairs)

            # make a backup copy
            if 'archive' not in path:
                self.backup()

        else:
            # functions to create DataFrames filled with null or good data as appropriate
            nullDF = lambda val : self._fillDF(val, columns, index)
            goodDF = lambda data: pd.DataFrame(data=data, columns=columns, index=index)
            DF = lambda data, val: nullDF(val) if data is None else goodDF(data)

            # create tables
            self.tables = map(DF, [values, errpos, errneg, refs], self.nullValues)
            self.values, self.errpos, self.errneg, self.refs = self.tables

            # check that all reference keys are defined
            for ref in self.refs.values.ravel():
                self.checkRef(ref)

            # write to disk
            if not os.path.exists(path):
                os.mkdir(path)
            if not os.path.exists(self.archive):
                os.mkdir(self.archive)

            self.save()


    def set(self, index, col, value=None, errpos=None, errneg=None, ref=None):
        """
        Set the value of an item in the catalog in-place, using null values for any keywords with None values and save
        to disk.

        Parameters
        ----------
        index, col: str
            Index and column locating the item in the catalog (e.g. 'alpha cen', 'distance'). Either index or column
            can be an iterable to allow setting values for the multiple rows in the same column or multiple columns
            of the same row at once, but not both!
        value, errpos, errneg : flt
            Value and errors (positive and negative) for the item.
        ref : str
            Reference key for the item.

        Returns
        -------
        None
        """
        data = [value, errpos, errneg, ref]

        iterI, iterC = [hasattr(x, '__iter__') for x in [index, col]]

        if iterI and iterC:
            raise TypeError('Only one of index and col can be iterable.')

        def groomLen(n):
            for i in range(len(data)):
                if data[i] is None:
                    data[i] = [data[i]]*n
                elif len(data[i]) != n:
                    raise ValueError('Given your input for index and col, value, errpos, errneg, and ref must all be '
                                     'iterables of length {} or be None.'.format(n))

        if iterI:
            groomLen(len(index))
            for i, v, ep, en, r in zip(index, *data):
                self._setSingle(i, col, v, ep, en, r)
        elif iterC:
            groomLen(len(col))
            for c, v, ep, en, r in zip(col, *data):
                self._setSingle(index, c, v, ep, en, r)
        else:
            self._setSingle(index, col, *data)

        self.save()


    def _setSingle(self, index, col, value=None, errpos=None, errneg=None, ref=None):
        """
        Like set method, but works with only a single value.
        """
        kwargs = dict(zip(self.keys, [value, errpos, errneg, ref]))
        for i, key in enumerate(self.keys):
            if kwargs[key] is not None:
                self.tables[i][col][index] = kwargs[key]
            else:
                self.tables[i][col][index] = self.nullValues[i]

        if 'ref' in kwargs:
            self.checkRef(kwargs['ref'])


    def __getitem__(self, key):
        return self.values[key]


    def __len__(self):
        return len(self.values)


    def strItem(self, index, col):
        """
        Return a plain-text representation of the catalog item with the errors and reference.
        """
        i, c = index, col
        return "{} (+{}, -{}) [{}]".format(self.values[i][c], self.errpos[i][c], self.errneg[i][c], self.refs[i][c])


    def printItem(self, index, col):
        """
        Print an item from the catalog with value, errors, and reference.
        """
        print self.strItem(index, col)


    def backup(self):
        """
        Backup the catalog by saving a copy of it in the archive subdirectory in a date+time stamped directory.
        """
        strTime = time.strftime("%Y%m%dT%H%M%S")
        archiveDir = os.path.join(self.path, 'archive', strTime)
        os.mkdir(archiveDir)

        tblPaths = [os.path.join(archiveDir, name) + '.' + self.fileSuffix for  name in self.tableFiles]
        for tbl, path in zip(self.tables, tblPaths):
            tbl.to_csv(path)

        refPath = os.path.join(archiveDir, self.refDictFile) + '.' + self.refFileSuffix
        self._saveRefDict(refPath)


    def copy(self, path):
        """
        Copy the catalog to a new path on the disk and return the copied object.
        """

        new = SciCatalog(path, self.values, self.errpos, self.errneg, self.refs, self.refDict)
        new.save()

        return new


    def save(self):
        """
        Write the SciCatalog to the disk (creating a set of files in self.path). This is useful if you have been
        tinkering with the table entries manually (i.e. via attributes rather than with the object methods).
        """

        # save tables
        for tbl, path in zip(self.tables, self.paths):
            tbl.to_csv(path)

        self._saveRefDict()


    def checkRef(self, refkey):
        """
        Check whether there is an entry in the reference dictionary for refKey. Issue warning if not.
        """
        if refkey not in ['none', None] and refkey not in self.refDict:
            warn("The reference key {} is not in the reference dictionary for this catalog. "
                 "You can add it with the `addRefEntry` method.".format(refkey))


    def addRefEntry(self, refkey, definition):
        """
        Add an entry to the reference dictionary in place and save to disk.

        Parameters
        ----------
        refKey : str
            The key (abbreviation) used to represent the reference.
        definition : str
            The expanded reference. No restrictions are placed on this -- it's up to you to decide how to format your
            references.

        Returns
        -------
        None
        """
        # warn user if about to replace an entry
        if refkey in self.refDict:
            warn("The reference \n\n"
                 "\t{rk} : {old} \n\n"
                 "is already in the dictionary. Replacing with\n\n"
                 "\t{rk} : {new} \n"
                 "".format(rk=refkey, old=self.refDict[refkey], new=definition))

        self.refDict[refkey] = definition

        self._saveRefDict()


    def addCol(self, colname):
        """
        Adds a column initialized with null values to the catalog in place and saves to disk.

        Parameters
        ----------
        colname : str
            Name for the new column.

        Returns
        -------
        None
        """
        index = self.values.index
        for tbl, val, path in zip(self.tables, self.nullValues, self.paths):
            tbl[colname] = pd.Series(data=[val]*len(self), index=index)
            tbl.to_csv(path)


    def addRow(self, index):
        """
        Adds a row initialized with null values to the catalog in place and saves to disk.

        Parameters
        ----------
        index : str
            Index for the row, e.g. name of a star in a catalog of stellar properties.

        Returns
        -------
        None
        """
        n = self.values.shape[1]
        for tbl, val, path in zip(self.tables, self.nullValues, self.paths):
            tbl.loc[index] = [val]*n
            tbl.to_csv(path)


    def colnames(self):
        """
        Return a list of the column names.
        """
        return list(self.values.columns)

    def indices(self):
        """
        Return a list of the indices (aka rows identifiers).
        """
        return list(self.values.index)


    def _saveRefDict(self, path=None):
        """
        Write the object's reference dictionary to the disk.
        """

        # save reference key
        if path is None:
            path = self.refDictPath
        with open(path, 'w') as f:
            for key, ref in self.refDict.iteritems():
                f.write('{} : {}\n'.format(key, ref))


    @classmethod
    def _fillDF(cls, val, columns, index):
        """
        Create a DataFrame filled with the same values.
        """
        data = [[val]*len(columns)]*len(index)
        return pd.DataFrame(data=data, columns=columns, index=index)


    @classmethod
    def _tablepaths(cls, path):
        return [os.path.join(path, name) + '.' + cls.fileSuffix for name in cls.tableFiles]