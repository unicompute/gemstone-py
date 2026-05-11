| created version |
created := OrderedCollection new.
version := '1'.

(UserGlobals includesKey: #GStoreRoot) ifFalse: [
  UserGlobals at: #GStoreRoot put: StringKeyValueDictionary new.
  created add: 'GStoreRoot'
].

(UserGlobals includesKey: #GSQueryRoot) ifFalse: [
  UserGlobals at: #GSQueryRoot put: Dictionary new.
  created add: 'GSQueryRoot'
].

(UserGlobals includesKey: #GemstonePyBootstrapVersion) ifFalse: [
  created add: 'GemstonePyBootstrapVersion'
].
UserGlobals at: #GemstonePyBootstrapVersion put: version.

'gemstone-py bootstrap ', version, ' created: ', created asArray printString
