# http://clang.llvm.org/doxygen/Index_8h_source.html
from enum import IntEnum


class TranslationUnitFlags(IntEnum):
    """控制翻译的行为"""
    None_ = 0x0
    # Used to indicate that the parser should construct a "detailed" preprocessing record,
    # including all macro definitions and instantiations.
    DetailedPreprocessingRecord = 0x01
    Incomplete = 0x02
    # Used to indicate that the translation unit should be built with an implicit precompiled header for the preamble.
    PrecompiledPreamble = 0x04
    CacheCompletionResults = 0x08
    # Used to indicate that the translation unit will be serialized with clang_saveTranslationUnit.
    # This option is typically used when parsing a header with the intent of producing a precompiled header.
    ForSerialization = 0x10
    # DEPRECATED
    CXXChainedPCH = 0x20
    # Used to indicate that function/method bodies should be skipped while parsing.
    # This option can be used to search for declarations/definitions while  ignoring the usages.
    SkipFunctionBodies = 0x40
    IncludeBriefCommentsInCodeCompletion = 0x80
    # Used to indicate that the precompiled preamble should be created on the first parse.
    # Otherwise it will be created on the first reparse. This trades runtime on the first parse (serializing the preamble takes time)
    # for reduced runtime on the second parse (can now reuse the preamble).
    CreatePreambleOnFirstParse = 0x100
    # Do not stop processing when fatal errors are encountered.
    KeepGoing = 0x200
    # Sets the preprocessor in a mode for parsing a single file only.
    SingleFileParse = 0x400
    # Used in combination with CXTranslationUnit_SkipFunctionBodies to constrain the skipping of function bodies to the preamble.
    LimitSkipFunctionBodiesToPreamble = 0x800
    # Used to indicate that attributed types should be included in CXType.
    IncludeAttributedTypes = 0x1000
    # Used to indicate that implicit attributes should be visited.
    VisitImplicitAttributes = 0x2000
    # Used to indicate that non-errors from included files should be ignored.
    IgnoreNonErrorsFromIncludedFiles = 0x4000
